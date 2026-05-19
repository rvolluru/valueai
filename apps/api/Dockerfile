FROM node:20-alpine AS web-build

WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json* ./
RUN npm install
COPY apps/web ./
ARG VITE_CLERK_PUBLISHABLE_KEY=""
ARG VITE_API_BASE_URL=""
ENV VITE_CLERK_PUBLISHABLE_KEY=${VITE_CLERK_PUBLISHABLE_KEY}
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN test -n "$VITE_CLERK_PUBLISHABLE_KEY"
RUN printf 'VITE_CLERK_PUBLISHABLE_KEY=%s\n' "$VITE_CLERK_PUBLISHABLE_KEY" > .env.production.local
RUN if [ -n "$VITE_API_BASE_URL" ]; then printf 'VITE_API_BASE_URL=%s\n' "$VITE_API_BASE_URL" >> .env.production.local; fi
RUN npm run build

FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY apps ./apps
COPY packages ./packages
COPY --from=web-build /web/dist ./apps/api/app/static

RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--app-dir", "apps/api", "--host", "0.0.0.0", "--port", "8000"]
