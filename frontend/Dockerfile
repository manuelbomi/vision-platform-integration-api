# Multi-stage build: compile the Vite/React admin dashboard, then serve the
# static output with nginx. Kept separate from the backend's Dockerfile
# (../Dockerfile) - this image only ever serves static files.

# --- build stage ---------------------------------------------------------
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Same default the app falls back to when unset (see src/api.ts) - override
# at build time to point the dashboard at a different backend.
ARG VITE_API_BASE_URL=http://127.0.0.1:8000
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build

# --- serve stage ----------------------------------------------------------
FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
