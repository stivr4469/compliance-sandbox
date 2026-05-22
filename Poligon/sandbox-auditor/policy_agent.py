import os
import json
import argparse
import logging
import requests
import subprocess
from typing import Optional, Dict, List
from openai import OpenAI
from dotenv import load_dotenv
from evidence_client import EvidenceClient
from slack_notifier import SlackNotifier
from constants import CONTROLS_MAP_FILE

load_dotenv()

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3-haiku")
EVIDENCE_TRACKER_URL = os.getenv("EVIDENCE_TRACKER_URL", "http://localhost:8000")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

POLICY_CONTROLS = {
    "CC1.1": {
        "title": "Information Security and Ethical Values Policy",
        "description": "Commitment to integrity and ethical values by management",
        "audience": "All employees, management, board"
    },
    "CC1.2": {
        "title": "Corporate Governance and Board Oversight Policy",
        "description": "Board independence, oversight structure, and governance responsibilities for security",
        "audience": "Board of Directors, C-suite, Legal"
    },
    "CC1.3": {
        "title": "Organizational Structure and Reporting Lines Policy",
        "description": "Management hierarchy, reporting relationships, and accountability structure",
        "audience": "All employees, HR, Management"
    },
    "CC1.4": {
        "title": "Security Awareness Training Policy",
        "description": "Commitment to attract, develop and retain competent individuals",
        "audience": "HR, All employees"
    },
    "CC1.5": {
        "title": "Accountability and Disciplinary Action Policy",
        "description": "Mechanisms to hold individuals accountable for internal control responsibilities",
        "audience": "HR, Management, Legal"
    },
    "CC2.2": {
        "title": "Internal Communication Policy",
        "description": "Internal communication of security objectives and responsibilities",
        "audience": "All employees"
    },
    "CC2.3": {
        "title": "External Communication and Privacy Policy",
        "description": "External communication on data handling, privacy practices and security commitments",
        "audience": "Customers, public, regulators"
    },
    "CC3.1": {
        "title": "Risk Assessment Objectives and Risk Appetite Policy",
        "description": "Specification of business objectives, risk tolerance and risk appetite statements",
        "audience": "Management, Board, Security team"
    },
    "CC3.2": {
        "title": "Risk Identification and Analysis Policy",
        "description": "Risk identification, analysis and response procedures",
        "audience": "Management, Security team"
    },
    "CC3.3": {
        "title": "Fraud Risk Assessment Policy",
        "description": "Assessment of fraud risk scenarios including misappropriation, corruption, and reporting fraud",
        "audience": "Management, Finance, Legal, Internal Audit"
    },
    "CC4.1": {
        "title": "Monitoring Activities and Control Evaluation Policy",
        "description": "Ongoing and separate evaluations of internal controls effectiveness",
        "audience": "Management, Compliance team, Internal Audit"
    },
    "CC5.1": {
        "title": "Control Activities Selection Policy",
        "description": "Selection and development of control activities to mitigate risks",
        "audience": "Management, Compliance team"
    },
    "CC5.3": {
        "title": "Change Management Policy",
        "description": "Deployment of changes through policies and procedures",
        "audience": "Engineering, DevOps"
    },
    "CC7.4": {
        "title": "Incident Response Policy",
        "description": "Incident response program including detection, response and recovery",
        "audience": "Security team, Engineering, Management"
    },
    "CC9.1": {
        "title": "Business Continuity Policy",
        "description": "Risk mitigation for business disruptions and recovery procedures",
        "audience": "Management, All employees"
    },
    "CC9.2": {
        "title": "Vendor Management Policy",
        "description": "Vendor and business partner risk assessment and management",
        "audience": "Procurement, Management, Legal"
    }
}

# 9 контролей, которые закрываются только через governance-документы
GOVERNANCE_CONTROLS = {
    "CC1.2", "CC1.3", "CC1.5",
    "CC2.3",
    "CC3.1", "CC3.2", "CC3.3",
    "CC4.1",
    "CC5.1",
}

class PolicyAgent:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, use_gemini_cli: bool = False):
        self.use_gemini_cli = use_gemini_cli
        if not use_gemini_cli:
            self.client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key,
                default_headers={
                    "HTTP-Referer": "compliance-sandbox",
                    "X-Title": "Compliance Sandbox Auditor",
                }
            )
            self.model = model

    def fetch_recent_violations(self) -> List[str]:
        try:
            resp = requests.get(f"{EVIDENCE_TRACKER_URL}/api/v1/evidence/?limit=50", timeout=10)
            resp.raise_for_status()
            evidence = resp.json()
            # Extract basic info from evidence for prompt
            return [f"{ev.get('title')} ({ev.get('source')})" for ev in evidence]
        except Exception as e:
            logger.warning(f"Could not fetch recent violations: {e}")
            return []

    def fetch_failed_controls(self) -> List[str]:
        try:
            resp = requests.get(f"{EVIDENCE_TRACKER_URL}/api/v1/controls/?limit=100", timeout=10)
            resp.raise_for_status()
            controls = resp.json()
            return [c['code'] for c in controls if c.get('status', '').upper() == "FAIL"]
        except Exception as e:
            logger.warning(f"Could not fetch failed controls: {e}")
            return []

    def collect_environment_context(self) -> dict:
        return {
            "company_name": os.getenv("COMPANY_NAME", "Acme Corp"),
            "github_repo": os.getenv("GITHUB_REPO", ""),
            "okta_domain": os.getenv("OKTA_DOMAIN", ""),
            "slack_channel": "#compliance-alerts",
            "aws_region": os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
            "evidence_tracker_url": EVIDENCE_TRACKER_URL,
            "recent_violations": self.fetch_recent_violations(),
            "failed_controls": self.fetch_failed_controls(),
        }

    def generate_policy(self, control_code: str, control_info: dict, env_context: dict) -> str:
        prompt = f"""You are a compliance expert writing SOC 2 Type II policies for a real company.

Write a professional policy document for control {control_code}: {control_info['title']}.

COMPANY CONTEXT (use these real details in the policy):
- Company name: {env_context['company_name']}
- GitHub repository: {env_context['github_repo']}
- Identity provider: Okta ({env_context['okta_domain']})
- Incident escalation channel: Slack {env_context['slack_channel']}
- Cloud infrastructure: AWS ({env_context['aws_region']}) via LocalStack for testing
- Compliance dashboard: {env_context['evidence_tracker_url']}

CURRENT COMPLIANCE STATE (reference these real findings in the policy):
- Controls currently FAILING: {env_context['failed_controls']}
- Recent violations found: {env_context['recent_violations'][:5]}

POLICY REQUIREMENTS:
- Write in English
- Reference the real tools and systems listed above (not generic placeholders)
- Structure: Purpose | Scope | Policy Statement | Responsibilities | Procedures | Enforcement | Review Cycle
- Be specific: name actual systems, tools, roles
- Length: 500-700 words
- Format: Markdown with ## headers

Return ONLY the policy document text, no explanations or preamble."""

        try:
            if self.use_gemini_cli:
                result = subprocess.run(
                    ["gemini", "-p", prompt, "-y"],
                    input=prompt,
                    capture_output=True, text=True, timeout=180
                )
                if result.returncode != 0:
                    raise Exception(f"Gemini CLI error: {result.stderr}")
                output = result.stdout
                # Обрезать Gemini-internal Task Status section
                for marker in ["---\n\n### Task Status", "---\n\n## Task", "\n### Task Status", "\n## Статус:"]:
                    if marker in output:
                        output = output[:output.index(marker)]
                # Убрать служебные строки CLI
                lines = output.splitlines()
                clean = [l for l in lines if not any(x in l for x in [
                    "Ripgrep", "MCP issues", "Error executing tool",
                    "Falling back", "YOLO mode"
                ])]
                return "\n".join(clean).strip()
            else:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error generating policy for {control_code}: {e}")
            raise

def main(controls_map: dict | None = None):
    parser = argparse.ArgumentParser(description="AI Policy Generator Agent")
    parser.add_argument("--control", type=str, help="Generate policy for a specific control code")
    parser.add_argument("--list", action="store_true", help="List all controls requiring policies")
    parser.add_argument("--company", type=str, help="Override company name for the policy")
    parser.add_argument("--gemini", action="store_true", help="Use Gemini CLI instead of OpenRouter")
    parser.add_argument("--governance", action="store_true", help="Generate only the 9 governance docs (CC1.2/1.3/1.5/2.3/3.1/3.2/3.3/4.1/5.1)")
    
    args = parser.parse_args()

    if args.list:
        print("Controls requiring policies:")
        for code, info in POLICY_CONTROLS.items():
            print(f"- {code}: {info['title']}")
        return

    use_gemini = args.gemini
    if not use_gemini and not OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY not found. Use --gemini flag to use Gemini CLI instead.")
        return

    agent = PolicyAgent(
        api_key=OPENROUTER_API_KEY if not use_gemini else None,
        model=OPENROUTER_MODEL if not use_gemini else None,
        use_gemini_cli=use_gemini
    )
    evidence_client = EvidenceClient(EVIDENCE_TRACKER_URL, agent_name="policy_agent")
    notifier = SlackNotifier(SLACK_WEBHOOK_URL) if SLACK_WEBHOOK_URL else None

    # Load controls map if not provided
    if controls_map is None:
        if not os.path.exists(CONTROLS_MAP_FILE):
            logger.error(f"{CONTROLS_MAP_FILE} not found. Run controls_seed.py first.")
            return
        with open(CONTROLS_MAP_FILE, "r") as f:
            controls_map = json.load(f)

    # Collect context once
    print("[AI] Collecting environment context...")
    env_context = agent.collect_environment_context()
    if args.company:
        env_context["company_name"] = args.company
        
    print(f"[AI] Context: company={env_context['company_name']}, "
          f"github={env_context['github_repo']}, "
          f"failed_controls={env_context['failed_controls']}")

    controls_to_process = POLICY_CONTROLS
    if args.governance:
        controls_to_process = {k: v for k, v in POLICY_CONTROLS.items() if k in GOVERNANCE_CONTROLS}
    elif args.control:
        if args.control in POLICY_CONTROLS:
            controls_to_process = {args.control: POLICY_CONTROLS[args.control]}
        else:
            logger.error(f"Control {args.control} is not in the policy controls list.")
            return

    for code, info in controls_to_process.items():
        if code not in controls_map:
            print(f"[SKIP] {code} not in controls_map.json")
            continue

        print(f"[AI] Generating policy for {code}: {info['title']}...")
        try:
            policy_text = agent.generate_policy(code, info, env_context)
            
            # Save to Evidence Tracker
            content = json.dumps({
                "policy_title": info["title"],
                "control": code,
                "generated_by": f"AI ({OPENROUTER_MODEL} via OpenRouter)",
                "environment": {
                    "github_repo": env_context["github_repo"],
                    "okta_domain": env_context["okta_domain"],
                    "company": env_context["company_name"]
                },
                "status": "DRAFT — requires human review and approval",
                "policy_text": policy_text
            })
            
            evidence_client.create_evidence(
                control_id=controls_map[code],
                title=f"[AI Draft] {info['title']}",
                content=content,
                source="AI_GENERATED"
            )
            evidence_client.update_control_status(controls_map[code], "PASS")
            print(f"[AI] Policy saved to Evidence Tracker: {code}")

            # Notify Slack
            if notifier:
                notifier.send({
                    "text": (
                        f"📄 *Policy Draft Ready: {code}*\n"
                        f"*{info['title']}*\n"
                        f"_Generated for {env_context['company_name']} "
                        f"({env_context['github_repo']})_\n"
                        f"Review: `{EVIDENCE_TRACKER_URL}/docs`"
                    )
                })
                print(f"[SLACK] Notification sent for {code}")
                
        except Exception as e:
            logger.error(f"Failed to process {code}: {e}")

if __name__ == "__main__":
    main()
