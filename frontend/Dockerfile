# Storefront image: static site served by unprivileged nginx (runs as UID 101 on port 8080).
# /api/* is proxied to the product API Service (name set via API_UPSTREAM).
FROM nginxinc/nginx-unprivileged:1.27-alpine
USER root
# pick up OS security fixes so Trivy stays green
RUN apk upgrade --no-cache
ENV API_UPSTREAM=phoenix-backend:8080
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY public/ /usr/share/nginx/html/
ARG APP_VERSION=dev
RUN echo "{\"version\":\"${APP_VERSION}\"}" > /usr/share/nginx/html/version.json
USER 101
EXPOSE 8080
