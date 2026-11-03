FROM node:20-alpine AS builder

WORKDIR /app

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ .
RUN npm run build

# Image de production avec Nginx
FROM nginx:1.25-alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY docker/nginx/nginx-frontend.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
