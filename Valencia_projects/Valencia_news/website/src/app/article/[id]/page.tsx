'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import type { Article, ChannelId } from '@/types'
import { CHANNELS } from '@/types'
import { isSafeUrl } from '@/lib/url'

const CHANNEL_EMOJI: Record<string, string> = {
  news: '📰',
  events: '🎭',
  tourism: '🏖️',
  gastronomy: '🍷',
}

function formatDate(iso: string): string {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('ru-RU', {
    day: 'numeric', month: 'long', year: 'numeric',
  })
}

export default function ArticlePage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const [article, setArticle] = useState<Article | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function findArticle() {
      for (const ch of CHANNELS) {
        try {
          const res = await fetch(`/data/${ch.id}.json`)
          if (!res.ok) continue
          const data = await res.json()
          const found = data.articles?.find((a: Article) => String(a.id) === String(id))
          if (found) {
            setArticle(found)
            setLoading(false)
            return
          }
        } catch {
          // канал недоступен — продолжаем поиск
        }
      }
      setLoading(false)
    }
    findArticle()
  }, [id])

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center"
        style={{ background: 'linear-gradient(135deg, #0d9488 0%, #0891b2 50%, #1d4ed8 100%)' }}>
        <div className="text-white text-lg">Загрузка...</div>
      </div>
    )
  }

  if (!article) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4"
        style={{ background: 'linear-gradient(135deg, #0d9488 0%, #0891b2 50%, #1d4ed8 100%)' }}>
        <div className="text-white text-xl">Статья не найдена</div>
        <button onClick={() => router.push('/')}
          className="text-white/70 hover:text-white underline text-sm">
          ← На главную
        </button>
      </div>
    )
  }

  const channelLabel = CHANNELS.find(c => c.id === (article.channel as ChannelId))?.label ?? article.channel

  return (
    <div className="min-h-screen"
      style={{ background: 'linear-gradient(135deg, #0d9488 0%, #0891b2 50%, #1d4ed8 100%)' }}>
      <div className="max-w-2xl mx-auto px-4 py-8">

        {/* Кнопка назад */}
        <button onClick={() => router.push('/')}
          className="flex items-center gap-1.5 mb-6 text-white/70 hover:text-white transition-colors text-sm">
          ← Назад
        </button>

        <article
          className="rounded-2xl overflow-hidden"
          style={{ background: 'rgba(255,255,255,0.12)', backdropFilter: 'blur(12px)', border: '1px solid rgba(255,255,255,0.2)' }}>

          {isSafeUrl(article.image_url) && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={article.image_url!}
              alt={article.title_ru}
              className="w-full h-56 object-cover"
              style={{ objectPosition: 'center 20%' }}
            />
          )}

          <div className="p-6">
            {/* Метаданные */}
            <div className="flex items-center gap-2 mb-4 text-xs" style={{ color: 'rgba(255,255,255,0.55)' }}>
              <span>{CHANNEL_EMOJI[article.channel] ?? '📄'}</span>
              <span>{channelLabel}</span>
              <span>·</span>
              <span>{article.source_name}</span>
              <span>·</span>
              <span>{formatDate(article.published_at)}</span>
            </div>

            {/* Заголовок */}
            <h1 className="text-white font-bold text-xl leading-snug mb-4">
              {article.title_ru}
            </h1>

            {/* Полное резюме */}
            <p className="text-base leading-relaxed mb-6" style={{ color: 'rgba(255,255,255,0.9)' }}>
              {article.summary_ru}
            </p>

            {/* Ссылка на оригинал */}
            {isSafeUrl(article.url) && (
              <a
                href={article.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-colors"
                style={{ background: 'rgba(255,255,255,0.2)', color: 'white' }}
                onMouseOver={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.3)')}
                onMouseOut={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.2)')}
              >
                Читать оригинал на {article.source_name} →
              </a>
            )}
          </div>
        </article>
      </div>
    </div>
  )
}
