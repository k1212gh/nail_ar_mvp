# 컨텍스트 = platform/ (docker build -f apps/server/Dockerfile .)
# 백엔드 + 빌드된 웹(apps/desktop/dist)을 한 컨테이너로 서빙. SQLite(/data 볼륨).
FROM node:20-slim
RUN apt-get update && apt-get install -y --no-install-recommends openssl ca-certificates && rm -rf /var/lib/apt/lists/*
RUN corepack enable
WORKDIR /app
COPY pnpm-workspace.yaml package.json tsconfig.base.json ./
COPY packages/shared ./packages/shared
COPY apps/server ./apps/server
COPY apps/desktop/dist ./apps/desktop/dist
# .env 무시(ENV 주입) + 빌드용 워크스페이스는 shared+server만
RUN rm -f apps/server/.env
RUN printf 'packages:\n  - "packages/shared"\n  - "apps/server"\n' > pnpm-workspace.yaml
RUN pnpm install --no-frozen-lockfile
WORKDIR /app/apps/server
RUN pnpm prisma generate
ENV WEB_DIR=/app/apps/desktop/dist
ENV DATABASE_URL=file:/data/prod.db
ENV PORT=3001
ENV RELAY_BASE=http://161.33.176.78:8090
ENV RELAY_VIEW_TOKEN=0fe58e809a663293ac059252c0d181d8
EXPOSE 3001
# 런타임에 볼륨(/data)에 db 생성 + 시드 + 서버
CMD ["sh","-c","pnpm exec prisma db push --skip-generate && (pnpm exec tsx src/seed.ts || true) && pnpm exec tsx src/index.ts"]
