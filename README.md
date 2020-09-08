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

- Connect to `db` DB container
```bash
docker exec -it binfundock_db_1 /bin/bash
```

- Apply migrations into the container
```bash
./manage.py migrate
```


