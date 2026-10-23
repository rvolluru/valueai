export function socialWebUrl(target, { shareUrl, imageUrl, caption }) {
  const url = shareUrl || imageUrl;
  if (!url) return null;
  return target === 'facebook'
    ? `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(url)}`
    : `https://www.pinterest.com/pin/create/button/?url=${encodeURIComponent(url)}${imageUrl ? `&media=${encodeURIComponent(imageUrl)}` : ''}&description=${encodeURIComponent(caption || '')}`;
}

export function shareWasCancelled(error) {
  return /cancel|dismiss|did not share|user did not/i.test(String(error?.message || error?.code || error || ''));
}

export async function shareSocialListing({ target, payload, platform, nativeShare, systemShare, browserFallback, openFacebook }) {
  const url = payload.shareUrl || payload.imageUrl;
  // Personal-profile posting remains a user action in Facebook's composer.
  // iOS's generic share sheet cannot select Facebook's extension for the user.
  if (target === 'facebook' && platform === 'ios') {
    const facebookUrl = socialWebUrl(target, payload);
    if (!facebookUrl) return;
    return openFacebook(facebookUrl);
  }
  try {
    if (platform === 'android' && nativeShare && url) {
      const packageName = target === 'facebook' ? 'com.facebook.katana' : 'com.pinterest';
      const installed = await nativeShare.isPackageInstalled(packageName);
      if (!installed.isInstalled) return browserFallback();
      // Facebook controls its own caption; share the public listing link rather than prefilled text.
      return await nativeShare.shareSingle({
        social: target === 'facebook' ? nativeShare.Social.FACEBOOK : nativeShare.Social.PINTEREST,
        url, title: payload.title, ...(target === 'pinterest' ? { message: payload.caption } : {}),
        failOnCancel: false,
      });
    }
    // iOS exposes installed apps through their share extensions. Do not use obsolete URL schemes.
    return await systemShare(platform === 'ios'
      ? { title: payload.title, ...(url ? { url } : { message: payload.caption }) }
      : { title: payload.title, message: [payload.caption, url].filter(Boolean).join('\n') },
    { dialogTitle: `Share to ${target === 'facebook' ? 'Facebook' : 'Pinterest'}` });
  } catch (error) {
    if (shareWasCancelled(error)) return;
    return browserFallback();
  }
}
