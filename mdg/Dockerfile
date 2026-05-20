FROM php:8.4-cli-alpine

RUN apk add --no-cache postgresql-dev \
    && docker-php-ext-install pdo pdo_pgsql

WORKDIR /app

COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

COPY composer.json ./
RUN composer install --no-dev --optimize-autoloader --no-interaction

COPY . .

RUN composer dump-autoload --optimize

EXPOSE 9000
CMD ["php", "-S", "0.0.0.0:9000", "-t", "public"]
