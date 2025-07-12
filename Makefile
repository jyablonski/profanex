.PHONY: test
test:
	@docker compose -f docker/docker-compose-test.yaml up --exit-code-from profanex_test_runner

.PHONY: tox-test
tox-test:
	@python -m tox
