t test:
	PYTHONPATH=. python tests/test_datastore.py

c cov cover coverage:
	coverage erase
	PYTHONPATH=. coverage run tests/test_datastore.py
	coverage html dropbox/datastore.py
	echo open htmlcov/index.html

docs:	dropbox/*.py doco.py
	sphinx-build -E -n . docs

d doco:
	python doco.py
