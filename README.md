scholar
========

Retrieve article information from Google Scholar in Python

Features
--------

 - Extract publication title, authors, year, citation count and number of online version
 - Format results in json, pickle, or nested dicts
 - FieldSets provide an easy way to update the scraper as the Scholar html layout changes
 - Command line interface to extract articles directly to terminal/file

Scholar is influenced heavily by [scholar.py](https://github.com/ckreibich/scholar.py) from Christian Kreibich, and includes a number of the patches that were incorporated into that. Scholar is currently being used inside a Django app as a Celery background task to periodically update paper information.

Scholar has been tested with Python 2.7 and 3.3

Example
-------

From the command line:

```bash
scholar.py --max_results 1
           --encoding json
           --file articles.json
           --author Marr
           Theory of edge detection
```

From within a Python project

```python
import scholar as gs
articles = gs.query(search='Theory of edge detection',
                    author='Marr',
                    max_results=1)

print(articles[0].dumps('json'))
```

WARNING!
--------
Google's Terms of Service strictly prohibit scraping any Google content, including Google Scholar. Using this package is in direct violation of their Terms of Service. You use it at your own risk, and bear any consequences Google imposes upon you.

If you DO decide to use this module, please be aware that scraping Google Scholar consumes Google bandwidth and resources, and doesn't provide revenue or compensation. If you run this scraper automatically, consider limiting the number of requests per day.
