.PHONY: test
test:
	@docker compose -f docker/docker-compose-test.yaml up --exit-code-from profanex_test_runner