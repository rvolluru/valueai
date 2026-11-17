import { useMemo, useState } from 'react'
import { SUPPORT_CATEGORIES, SUPPORT_CONTACT, searchSupportArticles, supportEmailUrl } from '../../../../packages/app-client/src/supportContent.mjs'

export default function SupportPage() {
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('All topics')
  const [contactTopic, setContactTopic] = useState('')
  const articles = useMemo(() => searchSupportArticles(query, category), [query, category])
  function resetSearch() { setQuery(''); setCategory('All topics') }
  return (
    <main className="support-page">
      <header className="support-page-header">
        <a className="legal-wordmark" href="/" aria-label="Jouft home">JOUFT</a>
        <a href="/">Back to Jouft</a>
      </header>
      <section className="support-hero" aria-labelledby="support-title">
        <p className="eyebrow">Here to help</p>
        <h1 id="support-title">Help &amp; Support</h1>
        <p>Find an answer, get unstuck, or reach the Jouft team.</p>
        <a href="#contact-jouft">Contact the team</a>
        <label className="support-search-label" htmlFor="support-search">Search help</label>
        <input id="support-search" className="support-search" type="search" value={query} onChange={event => setQuery(event.target.value)} maxLength={160} placeholder="Try “publish”, “AI preview”, or “shipping”" />
      </section>
      <nav className="support-categories" aria-label="Help topics">
        {['All topics', ...SUPPORT_CATEGORIES].map(topic => <button type="button" key={topic} aria-pressed={category === topic} onClick={() => setCategory(topic)}>{topic}</button>)}
      </nav>
      <div className="support-layout">
        <section className="support-answers" aria-labelledby="support-answers-title">
          <h2 id="support-answers-title">{category === 'All topics' ? 'Common questions' : category}</h2>
          <p className="support-result-count" role="status" aria-live="polite">{articles.length} {articles.length === 1 ? 'answer' : 'answers'}{query.trim() ? ' found' : ''}</p>
          {articles.length === 0 ? <div className="support-empty"><h3>No answers found</h3><p>Try a shorter search, choose another topic, or contact us.</p><button type="button" className="ghost" onClick={resetSearch}>Clear search and filters</button></div> : articles.map(article => (
            <details key={article.id} className="support-article" id={article.id}>
              <summary>{article.title}</summary>
              <div className="support-article-body">
                {article.body.map(paragraph => <p key={paragraph}>{paragraph}</p>)}
                {article.links?.map(link => <p key={link.path}><a href={link.path}>{link.label}</a></p>)}
              </div>
            </details>
          ))}
        </section>
        <aside id="contact-jouft" className="support-contact" aria-labelledby="support-contact-title">
          <p className="eyebrow">Still need a hand?</p>
          <h2 id="support-contact-title">Contact Jouft</h2>
          <p>For a listing problem, use <strong>Report issue</strong> on that listing when available so the request includes its context.</p>
          <label htmlFor="support-contact-topic">What do you need help with?</label>
          <select id="support-contact-topic" value={contactTopic} onChange={event => setContactTopic(event.target.value)}>
            <option value="">General support</option>
            {SUPPORT_CATEGORIES.map(topic => <option key={topic} value={topic}>{topic}</option>)}
          </select>
          <a className="support-email-button" href={supportEmailUrl(contactTopic)}>Email support</a>
          <p className="support-contact-note">Opens a draft in your email app. Review it and send it to contact us; opening the draft does not submit a request.</p>
          <p>If your email app does not open, write to <a href={supportEmailUrl()}>{SUPPORT_CONTACT.email}</a>.</p>
          <p>Phone: <a href={SUPPORT_CONTACT.phoneUrl}>{SUPPORT_CONTACT.phone}</a></p>
          <h3>What to include</h3>
          <ul><li>Your account email</li><li>Listing or trade reference, if relevant</li><li>What happened, what you expected, and steps to reproduce</li><li>Device and app/browser version; a screenshot with private details hidden</li></ul>
          <p>Never send passwords, verification codes, or full card details.</p>
          <nav className="support-policy-links" aria-label="Privacy and account information"><a href="/privacy">Privacy</a><a href="/terms">Terms</a><a href="/data-deletion">Data deletion</a></nav>
        </aside>
      </div>
    </main>
  )
}
