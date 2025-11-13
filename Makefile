ifeq (,$(wildcard .env))
$(error .env file is missing at . Please create one based on .env.example)
endif

include .env	
	
build-recollect:
	docker compose build

start-recollect:
	docker compose up --build -d

stop-recollect:
	docker compose stop
