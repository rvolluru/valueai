// srcdoc inherits the embedding page's base URL. Handle fragment links locally
// so they cannot navigate the sandbox to an unauthenticated application shell.
export function documentFrameHtml(html) {
  const navigation = `<script>
document.addEventListener('click', function(event) {
  if (event.defaultPrevented || event.button > 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  const link = event.target.closest && event.target.closest('a[href]');
  if (!link) return;
  const href = link.getAttribute('href');
  if (!href || href.charAt(0) !== '#' || link.hasAttribute('download')) return;
  event.preventDefault();
  let id;
  try { id = decodeURIComponent(href.slice(1)); } catch (_) { return; }
  const target = id ? document.getElementById(id) : document.documentElement;
  if (target) target.scrollIntoView({ behavior: 'auto', block: 'start' });
});
</script>`
  return html.includes('</body>') ? html.replace('</body>', `${navigation}</body>`) : html + navigation
}
