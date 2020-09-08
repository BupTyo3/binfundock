### Example `.env` File

```dotenv
SECRET_KEY=XXX
DEBUG=False

DB_HOST=db
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=postgres
```

### Docker 

- Start `web` and `db` containers
```bash
docker-compose -f docker-compose.yml up -d
```

- Run BASH commands or django SHELL `web` WEB container
```bash
docker exec -it pet-auction_web_1 /bin/bash
docker exec -it pet-auction_web_1 python manage.py shell
```

- Connect to `db` DB container
```bash
docker exec -it pet-auction_db_1 /bin/bash
```

- Apply migrations into the container
```bash
./manage.py migrate
```


