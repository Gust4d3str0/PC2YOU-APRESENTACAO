# Production-style image: static build served by `vite preview`. VITE_* values are baked in at build time.
FROM node:22-alpine AS build

WORKDIR /app

COPY --chown=node:node package*.json ./
RUN npm ci

COPY --chown=node:node . .

ARG VITE_DEMO_MODE=true
ARG VITE_CATALOG_API_URL=http://localhost:8012
ARG VITE_BUDGETS_API_URL=http://localhost:8013
ARG VITE_USERS_API_URL=http://localhost:8001
ENV VITE_DEMO_MODE=$VITE_DEMO_MODE \
    VITE_CATALOG_API_URL=$VITE_CATALOG_API_URL \
    VITE_BUDGETS_API_URL=$VITE_BUDGETS_API_URL \
    VITE_USERS_API_URL=$VITE_USERS_API_URL

RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 5173
CMD ["nginx", "-g", "daemon off;"]
