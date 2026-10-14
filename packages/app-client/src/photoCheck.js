export const PHOTO_CHECK_TIMEOUT_MS = 30000;
export const PHOTO_CHECK_TIMEOUT_MESSAGE = 'Photo check timed out. Your photos are safe. Select a category to continue; full item and pricing analysis will still run.';

export async function withPhotoCheckTimeout(operation, timeoutMs = PHOTO_CHECK_TIMEOUT_MS) {
  const controller = new AbortController();
  let timer;
  const deadline = new Promise((_, reject) => {
    timer = setTimeout(() => {
      const error = new Error(PHOTO_CHECK_TIMEOUT_MESSAGE);
      error.code = 'photo_check_timeout';
      reject(error);
      controller.abort();
    }, timeoutMs);
  });
  try { return await Promise.race([operation(controller.signal), deadline]); }
  finally { clearTimeout(timer); }
}
