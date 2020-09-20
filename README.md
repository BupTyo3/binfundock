### Example `.env` File

```dotenv
SECRET_KEY=XXX
DEBUG=False

DB_HOST=db
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=postgres
```

### Sample `config.ini` File

```ini
[Logic]
how_percent_for_one_signal=10
[Market]
market_api_key=xxx
market_api_secret=xxx
[Signal]
accessible_main_coins=USDT,
```

### Logs

- Create logs folder
```bash
mkdir logs
```

### Docker 

- Start `web` and `db` containers
```bash
docker-compose -f docker-compose.yml up -d
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
