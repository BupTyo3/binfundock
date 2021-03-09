### Example `.env` File
Required
```dotenv
SECRET_KEY=XXX

DB_HOST=db
DB_NAME=binfun_name
DB_USER=binfun_user
DB_PASSWORD=binfun_password_xxx

WEB_GLOB_PORT=8100
```
Optional
```dotenv
DEBUG=False
TELETHON_LOG_LEVEL=30
CELERY_LOG_LEVEL=20
```

### Sample `config.ini` File

```ini
[Logic]
common_period_of_cron_celery_tasks_secs=7.0
period_of_prices_update_tasks_secs=50.0
;for the lost sl orders below the current_price multiple delta param
extremal_sl_price_shift_coef=5.0
[Market]
market_api_key=xxx
market_api_secret=xxx
futures_market_api_key=xxx
futures_market_api_secret=xxx
market_fee=0.1
futures_market_fee=0.03
inviolable_balance_perc=15.0
market_futures_raw_url=https://www.binance.com/en/futures/{}?theme=dark
market_spot_raw_url=https://www.binance.com/en/trade/{}?theme=dark
[Signal]
# for table Signal
accessible_main_coins=USDT,
# For table SignalOrig
all_accessible_main_coins=USDT,BTC,ETH
[Telegram]
api_id
api_hash
chat_china_id
crypto_angel_id
```

### Logs

- Create logs folder
```bash
mkdir logs
mkdir parsed-images
```

### Others

- Create parsed-images folder
```bash
mkdir parsed-images
```

### Docker 

- Build containers
```bash
docker-compose build
```
- If problem with build
```bash
sudo chown <user>:<user> pgdata
```

- Build containers for separate AGGREGATOR service (SignalOrig)
```bash
docker-compose -f docker-compose-aggregator.yml build
```

- Start containers (without -d flag - not in daemon mode)
```bash
docker-compose up -d
```

- Start containers for separate AGGREGATOR service (without -d flag - not in daemon mode)
```bash
docker-compose -f docker-compose-aggregator.yml up -d
```

- Start specific containers (without -d flag - not in daemon mode)
```bash
docker-compose up -d web nginx celery
```

- Run BASH commands or django SHELL `web` WEB container
```bash
docker exec -it binfundock_web_1 /bin/bash
docker exec -it binfundock_web_1 python manage.py shell
```

- Apply migrations into the container
```bash
python manage.py migrate
```

- Connect to `db` DB container
```bash
docker exec -it binfundock_db_1 /bin/bash
```

- Remove `web`, `db` and `nginx` containers
```bash
docker rm binfundock_web_1 binfundock_db_1  binfundock_nginx_1
```

- Remove `web` image
```bash
docker image rm binfundock_web:latest
```


##### Commands into `web` container

- To work with django web you need to run server 
```bash
 python manage.py runserver
```

- Create superuser
```bash
python manage.py createsuperuser
```

##### Remove DB data completely. Be careful! Make a copy first! 
```bash
rm -r pgdata
```

### Add into AUTOLOAD after reboot
```bash
crontab -e
```
Add to the end of the file (change path_to_work_directory with yours)
```
@reboot /usr/local/bin/docker-compose -f /home/ubuntu/path_to_work_directory/binfundock/docker-compose.yml up -d > /dev/null
```


### DEVELOPMENT
#### Sample `binfun/local_settings.py` File

```python

DEBUG = True

# django_extensions
INTERNAL_IPS = '127.0.0.1'

```
#### SHELL_PLUS

- shell_plus
```bash
python manage.py shell_plus
```

- shell_plus with sql queries printing
```bash
python manage.py shell_plus --print-sql
```
