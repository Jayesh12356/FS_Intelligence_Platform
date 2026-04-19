FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 3001

# package.json's "dev" script runs ``next dev -p 3001`` to match the host
# dev workflow. Keep the container internal port aligned (compose maps
# 3001:3001) so a single port number is used everywhere.
CMD ["npm", "run", "dev"]
