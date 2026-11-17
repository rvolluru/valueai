// User-facing guidance shared by web and native clients. Keep it aligned with
// shipped controls; do not promise response times or automated resolutions.
export const SUPPORT_CONTACT = { email: 'admin@jouft.com', phone: '(949) 354-4133', phoneUrl: 'tel:+19493544133' };
export const SUPPORT_CATEGORIES = ['Getting started', 'Listings & photos', 'Analysis & AI previews', 'Marketplace & trades', 'Shipping & payments', 'Account & privacy', 'Troubleshooting'];
export const SUPPORT_ARTICLES = [
  { id: 'sign-in', category: 'Getting started', title: 'How do I sign in or recover my account?', keywords: 'login password forgot verification code google facebook invitation', body: [
    'Choose Log In or Sign In and use the same email address and sign-in method you used when joining. If access requires an invitation, use Request Access and follow the instructions shown.',
    'For an email-and-password account, choose Forgot password? and follow the verification steps. Check spam or junk folders if a message is missing. Use the most recent code and never share it with anyone.',
    'If you still cannot sign in, email support with your account email and the error message. Do not create another account to recover an existing closet.' ] },
  { id: 'profile', category: 'Getting started', title: 'What should I complete in my profile?', keywords: 'onboarding birthday age sizes style preferences address setup', body: [
    'Complete the profile steps shown after joining, including your name, birthday, style and size preferences, shipping details, and plan selection. Jouft requires members to be at least 18.',
    'Select the sizes you comfortably wear across brands and the categories you enjoy. You can update these preferences in Profile. Save your changes before leaving.',
    'Keep your shipping address current before agreeing to a trade. Review the selected plan and any displayed cost before confirming it.' ] },
  { id: 'create-listing', category: 'Listings & photos', title: 'How do I create a listing?', keywords: 'upload camera create closet add item photos', body: [
    'Open Create Listing and add clear photos of one item. Follow the photo prompts for its category: show the full item and relevant labels, size markings, details, and signs of wear.',
    'Use your own photos in good light. Keep the item in focus and avoid filters that change its color or hide its condition. Include any flaws.',
    'Confirm the category, size, and actual condition, then continue with the analysis. Creating or analyzing an item does not publish it; review the results and confirm publication separately.' ] },
  { id: 'item-condition', category: 'Listings & photos', title: 'What do the item condition types mean?', keywords: 'condition grades new with tags NWT unused unworn like new lightly used wear', body: [
    'New with tags: The item is unused and unworn, with its original tags still attached. Show the tags clearly in your photos and disclose any missing packaging or accessories.',
    'New: The item is unused and unworn, but does not have attached original tags. This is different from an item that has been worn, even briefly.',
    'Like new: The item has been lightly used and is in excellent condition, with little or no visible wear. It is not the same as unused or new.',
    'Choose the condition that describes your actual item, and photograph and describe any wear, marks, damage, alterations, or missing accessories. An original box alone does not make a worn item new. Jouft currently offers these three condition choices; if none accurately describes your item, contact support before publishing rather than overstating its condition.',
    'Check the selected condition during listing review. Condition affects estimated value, and an AI-generated preview does not establish the item’s condition.' ] },
  { id: 'listing-status', category: 'Listings & photos', title: 'Why is my listing a draft or waiting for review?', keywords: 'status analyzing active failed archived private publish', body: [
    'A draft or listing awaiting review has not completed publication. Analyzing means processing is still in progress; return to My Closet and refresh to check its latest status.',
    'Open Review and Publish when available. Check the product details, condition, value, size, and photos, and complete any missing information before confirming publication.',
    'Active listings are published. Archived listings are removed from the closet view without erasing existing trade history. If processing fails, inspect the message, correct the details where possible, or report a listing issue.' ] },
  { id: 'closet-search', category: 'Listings & photos', title: 'How do I find or update an item in My Closet?', keywords: 'search title brand category filter edit review missing listing', body: [
    'Search My Closet by title, brand, or category. Check the selected status filter and clear the search if you cannot find an item.',
    'Open the item’s available actions to edit it, review it, or inspect its details. Make sure you are signed into the account that owns the listing.',
    'If an item opens incorrectly or seems to be missing, contact support with its title and listing ID or link, plus a screenshot of what you see.' ] },
  { id: 'analysis', category: 'Analysis & AI previews', title: 'What do the analysis and estimated value mean?', keywords: 'valuation price authenticity brand model condition estimate', body: [
    'Analysis helps identify the item and estimate its value using available evidence. Check the suggested brand, model, description, condition, size, and pricing references against your item.',
    'Values are estimates, not guaranteed sale prices or offers. Differences in condition, model, materials, and available comparables can change the result.',
    'AI analysis and an AI styling preview are not authentication certificates. If identification or authenticity information looks wrong, report the issue rather than relying on it as proof.' ] },
  { id: 'wrong-analysis', category: 'Analysis & AI previews', title: 'What if the analysis is wrong or the value is $0?', keywords: 'incorrect wrong price zero missing value retry report issue', body: [
    'A missing or zero value can mean pricing evidence was insufficient or analysis did not complete. It does not mean the item is free.',
    'Check that the photos, category, size, and condition describe the correct item. Review any request for clearer photos or more information, then save corrections through the available listing controls.',
    'Email support with the listing ID or link, the expected result, and what appears incorrect. The in-app listing Report Issue control is temporarily hidden. A report is a request for review; it does not itself change the value or guarantee a rerun.' ] },
  { id: 'ai-preview', category: 'Analysis & AI previews', title: 'How do I choose whether to use an AI mannequin image?', keywords: 'mannequin generated synthetic preview include exclude original photos publish gallery', body: [
    'When an AI styling preview is available, inspect it alongside your original photos. Look for changes to the product’s shape, color, details, or fit.',
    'During listing review, choose Include mannequin image or Use original photos only when prompted. Complete the choice before confirming publication.',
    'An AI-generated image is a styling illustration, not a photo of the actual item or proof of fit or authenticity. Use originals only if the preview is inaccurate, and report an image issue if you need help.' ] },
  { id: 'marketplace', category: 'Marketplace & trades', title: 'Why am I not seeing Marketplace matches?', keywords: 'empty no matches search sizes categories preferences listings', body: [
    'Publish eligible listings and complete your profile so Jouft has information to find matches. Drafts are not published Marketplace items.',
    'Clear Marketplace search and filters, then refresh. Review your style, category, and size preferences; choose the sizes you actually wear rather than a single size across every brand.',
    'Matches depend on available listings and can change over time. If results still look wrong, send support an example of a published listing and the search or filters you used.' ] },
  { id: 'trade', category: 'Marketplace & trades', title: 'How do I send or respond to a trade proposal?', keywords: 'offer inbox accept decline proposal trade item', body: [
    'Open an item you want and choose Start Trade when available. Select your eligible offered item or items, review the proposal and displayed shipping information, and send it once.',
    'Open your Inbox to inspect incoming and outgoing proposals. Before accepting, check both items and select an offered item if prompted. Decline a proposal if it is not right for you.',
    'If the proposal has already changed or an action is unavailable, refresh before trying again. Do not assume a trade is accepted until its current status confirms it.' ] },
  { id: 'trade-problem', category: 'Marketplace & trades', title: 'How do I report a problem with a trade or received item?', keywords: 'damaged counterfeit fake wrong item dispute report issue', body: [
    'Keep the trade reference, listing details, messages, and clear photos of the item and packaging. Describe what happened and when.',
    'On the website, open the relevant trade in Inbox and use Report Trade Issue when available. If you cannot use that action, email support with the trade reference and your account email.',
    'Contact support for guidance before arranging a return or taking another action outside the displayed trade process. Reporting starts a review; it does not automatically issue a refund or resolve the case.' ] },
  { id: 'shipping', category: 'Shipping & payments', title: 'Where do I find shipping information or a label?', keywords: 'tracking delivery carrier label address package shipment', body: [
    'Open the accepted trade and review its shipment details. Use the label and tracking information provided when they are available, and check the destination before handing a parcel to the carrier.',
    'If a label is missing or the address is wrong, contact support with the trade or shipment reference before sending the item. Avoid creating a second paid label just to retry.',
    'For a delayed or missing shipment, include the tracking number, carrier, and the last tracking update in your support request. Keep your postage receipt and packaging photos.' ] },
  { id: 'billing', category: 'Shipping & payments', title: 'How do I manage my plan or report a payment problem?', keywords: 'subscription cancel card billing charge refund payment plan', body: [
    'Open Profile and the Subscription section to review the available plan controls. Payment-method controls are shown where supported. Review the amount and billing details before confirming a change.',
    'If you want to stop a subscription, use Cancel Subscription when offered and check the resulting status. Signing out or uninstalling the app does not cancel a subscription.',
    'For a failed, unexpected, or duplicate charge, contact support with the date, amount, currency, and related trade or payment reference. Never send a full card number, security code, or banking password. A support request does not itself cancel a payment or promise a refund.' ] },
  { id: 'email-updates', category: 'Account & privacy', title: 'How do I unsubscribe from daily match emails?', keywords: 'unsubscribe email updates daily feed notifications marketing subscribe', body: [
    'On the website, open My Profile, find Email updates in the general profile section, and choose Unsubscribe from email updates. Check the saved confirmation. You can subscribe again there later.',
    'You can also use the unsubscribe link in a daily match email. If you are using the mobile app and do not see this preference, open the website or use the email link.',
    'Daily match emails are sent only when there are new matches. The email-updates preference is separate from app activity notifications and messages required to service your account or transactions.' ] },
  { id: 'privacy', category: 'Account & privacy', title: 'How do I request account or personal-data deletion?', keywords: 'delete account remove data privacy facebook security password', body: [
    'Read the user data deletion instructions linked below and email support from the address associated with your account. Support will need to verify ownership.',
    'Removing Facebook Login access or uninstalling Jouft does not automatically delete your Jouft account or data. Some records may need to be retained for unresolved transactions or other obligations described in the privacy information.',
    'Do not send a password, verification code, or identity document in your initial request. If you cannot access your account email, explain that to support so they can advise on verification.' ], links: [{ label: 'User data deletion instructions', path: '/data-deletion' }, { label: 'Privacy Policy', path: '/privacy' }] },
  { id: 'app-problem', category: 'Troubleshooting', title: 'What should I try if the app, uploads, or a button stops working?', keywords: 'crash stuck loading keyboard button upload permissions camera photos network', body: [
    'Check your connection, then refresh the website or close and reopen the app. Use the latest available app build or browser. Before refreshing, preserve any unsaved text or photos you may need to enter again.',
    'For photo or camera problems, check the app’s requested permissions in device settings. If a file fails, try a clear photo in a supported format. If a button or field does not respond, note the screen and whether it happens after opening the keyboard or scrolling.',
    'If it continues, send support your device, operating system, browser or app version, steps to reproduce, and the exact error message. A screenshot is helpful; hide private messages, addresses, and payment details first.' ] },
];

export function searchSupportArticles(query = '', category = 'All topics') {
  const words = String(query).normalize('NFKC').toLocaleLowerCase('en-US').trim().split(/\s+/).filter(Boolean);
  return SUPPORT_ARTICLES.filter(article => (category === 'All topics' || article.category === category)
    && words.every(word => [article.title, article.category, article.keywords, ...article.body].join(' ').toLocaleLowerCase('en-US').includes(word)));
}

export function supportEmailUrl(topic = '') {
  return `mailto:${SUPPORT_CONTACT.email}?subject=${encodeURIComponent(topic ? `Jouft support: ${topic}` : 'Jouft support')}&body=${encodeURIComponent('Account email:\nDevice and app/browser version:\nListing or trade reference (if relevant):\nWhat happened:\nWhat I expected:\nSteps to reproduce:\n\nPlease do not include passwords, verification codes, or full payment details.')}`;
}
