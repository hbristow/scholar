#! /usr/bin/env python
"""
scholar
A module for retrieving article information from Google Scholar queries
"""

# ----------------------------------------------------------------------------
# Imports
# ----------------------------------------------------------------------------
from __future__ import print_function
import sys
import re

# URL loaders
try:
  # Python 3
  from http.cookiejar import CookieJar
  from urllib.parse import quote
  from urllib.request import HTTPCookieProcessor, Request, build_opener
  unicode = str
  encode = lambda s: s
except ImportError:
  # Python 2
  from cookielib import CookieJar
  from urllib import quote
  from urllib2 import HTTPCookieProcessor, Request, build_opener
  encode = lambda s: s.encode('utf8')

# DOM traversal
try:
  from bs4 import BeautifulSoup
except ImportError:
  try:
    from BeautifulSoup import BeautifulSoup
  except ImportError:
    sys.exit('Beautiful Soup is required')

# formatters
import json
import pickle


# ----------------------------------------------------------------------------
# Fieldsets and Helper objects
# ----------------------------------------------------------------------------
class Field(object):
  """
  A Field describes a unit of information to be scraper. Multiple Fields
  within a logical group form a FieldSet

  attributes:
    find    - A beautiful soup expression to retrieve the field from the
              current context (the FieldSet)
    type    - The type of the Field. Defaults to string
    default - The default value of the Field when a new FieldSet is created
  """
  def __init__(self, find=None, type=unicode, default=None):
    self.find = find
    self.type = type
    self.default = default


class AttributeDict(dict):
  """
  A dictionary with keys that can be accessed as attributes
  d['key'] == d.key
  """
  def __setattr__(self, key, val): self[key] = val
  def __getattr__(self, key): return self[key]


class FieldSet(object):
  """
  A set of Fields forming a logical set of information. A FieldSet must contain
  at least one attribute called 'find_all' which describes how a FieldSet can
  be extracted from the global soup.
  """
  def __init__(self):
    # internal meta fields
    self._fields = AttributeDict()

    # validate - make sure FieldSet has an 'expr' Field
    if 'find_all' not in dir(self):
      raise AttributeError(self.__class__.__name__ + ' requires an attribute named find_all')

    # move the fields into the FieldSet meta and rebind the actual fields
    for field in dir(self):
      obj = getattr(self, field)
      if isinstance(obj, Field):
        setattr(self._fields, field, obj)
        setattr(self, field, obj.default)

  @classmethod
  def name(cls):
    return cls.__name__.lower()

  @classmethod
  def name_plural(cls):
    try:
      return cls.name_plural.lower()
    except:
      return cls.name() + 's'

  def dumps(self, format=None):
    # create a dictionary representation of the FieldSet
    d = self._fields
    for key in d:
      d[key] = getattr(self, key)
    if format == 'json':
      import json
      return json.dumps(d, indent=2, ensure_ascii=False)
    return d


# ----------------------------------------------------------------------------
# Fetcher and Parser
# ----------------------------------------------------------------------------
class Fetcher(object):
  """
  Fetch URLs and maintain cookies
  """
  user_agent = 'Mozilla/5.0 (X11; U; FreeBSD i386; en-US; rv:1.9.2.9) Gecko/20100913 Firefox/3.6.9'

  def __init__(self):
    self.cookie_jar = CookieJar()
    self.opener = build_opener(HTTPCookieProcessor(self.cookie_jar))

  def fetch(self, url):
    request = Request(url=url, headers={'User-Agent': self.user_agent})
    return self.opener.open(request).read()


class Parser(object):
  """
  Parse html responses into Fieldsets
  """
  def parse(self, html, fieldset, max_results=10):
    soup = BeautifulSoup(html)
    results = []

    # parse out the fieldset
    matches = fieldset.find_all(soup)
    for index, match in zip(range(0, max_results), matches):
      # create a new insance of the fieldset
      inst = fieldset()
      # locate all of the article fields in the match
      for fieldname, field in inst._fields.items():
        try:
          value = field.type(field.find(match))
        except (TypeError, AttributeError):
          value = field.default
        setattr(inst, fieldname, value)
      results.append(inst)

    # return the results
    return results


# ----------------------------------------------------------------------------
# Article
# ----------------------------------------------------------------------------
class Article(FieldSet):
  """
  A concrete Fieldset for scraping article information from a
  Google Scholar query
  """
  find_all      = staticmethod(lambda soup: soup.find(role='main').find_all(class_="gs_ri"))
  title         = Field(lambda soup: soup.find('h3').text.lstrip('[PDF]').strip())
  authors       = Field(lambda soup: soup.find(class_='gs_a').text.split('-')[0].strip())
  year          = Field(lambda soup: re.search(r'[0-9]{4}', soup.find(class_='gs_a').text).group(0), type=int)
  num_citations = Field(lambda soup: re.search(r'Cited by ([0-9]+)', soup.text).group(1), type=int)
  num_versions  = Field(lambda soup: re.search(r'All ([0-9]+) versions', soup.text).group(1), type=int)
  url           = Field('')
  citations_url = Field('')
  versions_url  = Field('')


# ----------------------------------------------------------------------------
# query Google Scholar
# ----------------------------------------------------------------------------
def _format_url(query, author=''):
  url_spec = {
    'base': 'http://scholar.google.com/scholar?hl=en&btnG=Search&as_subj=eng&as_sdt=1,5&as_ylo=&as_vis=0',
    'query': '&q={query}',
    'author': '+author:{author}'
  }
  return (url_spec['base'] + url_spec['query'] + (url_spec['author'] if author else '')).format(
    query=quote(query), author=quote(author))


def query(search='', author='', max_results=10, fetcher=None, fieldset=Article):
  fetcher = fetcher if fetcher else Fetcher()
  parser = Parser()

  url = _format_url(search, author)
  response = fetcher.fetch(url)
  results = parser.parse(response, fieldset, max_results)
  return results


# ----------------------------------------------------------------------------
# Command Line Interface
# ----------------------------------------------------------------------------
if __name__ == '__main__':
  """
  Retrieve article information from Google Scholar on the command line. e.g.

    scholar.py --max_results 1 --encoding json --file articles.json --author Marr Theory of edge detection
  """
  import argparse

  # setup the parser
  parser = argparse.ArgumentParser(description='Retrieve article information from Google Scholar')
  parser.add_argument('-a', '--author', help='Author name', default='')
  parser.add_argument('-m', '--max_results', help='Maximum results to return', default=10)
  parser.add_argument('-f', '--file', help='Write the results to file')
  parser.add_argument('-e', '--encoding', help='Output encoding - dict, json, pickle', default='json')
  parser.add_argument('search_terms', nargs='+')

  # parse the named and positional arguments
  args = parser.parse_args()
  search = ' '.join(args.search_terms)

  # retrieve the articles
  articles = query(search, args.author, args.max_results)

  # format the articles
  merged = [article.dumps() for article in articles]
  formatted = {
    'dict':   lambda: merged,
    'json':   lambda: json.dumps(merged, indent=2, sort_keys=True, ensure_ascii=False),
    'pickle': lambda: pickle.dumps(merged),
  }.get(args.encoding, lambda: None)()

  # write the articles to file, or display them
  if args.file:
    with open(args.file, 'w') as f:
      f.write(formatted.encode('utf8'))
  else:
    print(formatted)
