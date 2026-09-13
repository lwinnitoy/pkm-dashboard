# Frontend image: build the Vite app, then serve the static bundle with nginx,
# which also reverse-proxies /api and /health to the backend (same-origin, no CORS).
FROM node:20-alpine AS build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
# Empty base = same-origin requests ("/api/..."), proxied by nginx below.
ARG VITE_API_BASE=""
ENV VITE_API_BASE=$VITE_API_BASE
RUN npm run build

FROM nginx:alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
