#!/bin/bash
set -a
source /Users/shotaro/line-news-bot/.env
set +a
/opt/anaconda3/bin/python3 /Users/shotaro/line-news-bot/news_bot.py >> /Users/shotaro/line-news-bot/news.log 2>&1
