FROM php:8.4-fpm-alpine

RUN apk add --no-cache nginx supervisor postgresql-dev \
    && docker-php-ext-install pdo pdo_pgsql opcache \
    && echo "opcache.enable=1\nopcache.memory_consumption=128\nopcache.max_accelerated_files=10000\nopcache.validate_timestamps=0" \
       > /usr/local/etc/php/conf.d/opcache.ini

# zz-docker.conf in the base image overrides listen to 0.0.0.0:9000; remove it
# so our www.conf (port 9001) takes effect without conflict with nginx on 9000
RUN rm -f /usr/local/etc/php-fpm.d/zz-docker.conf

WORKDIR /app

COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

COPY composer.json composer.lock ./
RUN composer install --no-dev --optimize-autoloader --no-interaction

COPY docker/www.conf /usr/local/etc/php-fpm.d/www.conf
COPY docker/nginx.conf /etc/nginx/nginx.conf
COPY docker/supervisord.conf /etc/supervisord.conf

COPY . .

RUN mkdir -p var/cache var/log \
    && chown -R www-data:www-data /app/var

EXPOSE 9000
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisord.conf"]
