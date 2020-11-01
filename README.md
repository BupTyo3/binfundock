### Example `.env` File

```dotenv
SECRET_KEY=XXX
DEBUG=False

DB_HOST=db
DB_NAME=binfun_name
DB_USER=binfun_user
DB_PASSWORD=binfun_password_xxx
```

### Sample `config.ini` File

```ini
[Logic]
[Market]
market_api_key=xxx
market_api_secret=xxx
futures_market_api_key=xxx
futures_market_api_secret=xxx
market_fee=0.1
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

- Start containers (without -d flag - not in daemon mode)
```bash
docker-compose up -d
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
