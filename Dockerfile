FROM python:alpine

WORKDIR /app

RUN apk update && apk upgrade
RUN apk add --no-cache \
  make \
  gcc \
  g++ \
  musl-dev \
  ca-certificates \
  jpeg-dev \
  zlib-dev \
  libjpeg \
  nss \
  freetype \
  harfbuzz \
  ttf-freefont \
  libexif \
  udev \
  xvfb \
  libpq-dev \
  chromium \
  chromium-chromedriver

RUN pip install --upgrade pip
RUN pip install selenium pyvirtualdisplay

ENV CHROME_BIN=/usr/bin/chromium-browser
ENV CHROME_PATH=/usr/lib/chromium/

COPY . .

RUN pip install -r requirements.txt

ENTRYPOINT ["python", "main.py"]
