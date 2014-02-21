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
  A dictionary with keys that can be accessed as attributes e.g. d['key'] == d.key
  NOTE: Causes a memory leak on Python < 2.7.3
  """
  def __init__(self, *args, **kwargs):
    super(AttributeDict, self).__init__(*args, **kwargs)
    self.__dict__ = self


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
    for field in self.fields():
      obj = getattr(self, field)
      setattr(self._fields, field, obj)
      setattr(self, field, obj.default)

  @classmethod
  def fields(self):
    try:
      return self._fields.keys()
    except AttributeError:
      return [field for field in dir(self) if isinstance(getattr(self, field), Field)]

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
    """
    create a serialized representation of the FieldSet
    format - 'dict'   a raw dictionary representation
             'json'   a json unicode string
             'pickle' a pickled representation
    """
    d = dict((key, getattr(self, key)) for key in self._fields)
    return {
      'json':   lambda: json.dumps(d, indent=2, ensure_ascii=False),
      'pickle': lambda: pickle.dumps(d)
    }.get(format, lambda: d)()


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
          value = field.type(field.find(match).strip())
        except (TypeError, AttributeError):
          value = field.default
        setattr(inst, fieldname, value)
      results.append(inst)

    # return the results
    return results


# ----------------------------------------------------------------------------
# Google Scholar URL spec
# ----------------------------------------------------------------------------
URL_ROOT   = 'http://scholar.google.com'
URL_META   = '/scholar?hl=en&btnG=Search&as_subj=eng&as_sdt=1,5&as_ylo=&as_vis=0'
URL_QUERY  = '&q={query}'
URL_AUTHOR = '+author:{author}'
def _format_url(query, author=''):
  return (URL_ROOT + URL_META + URL_QUERY + (URL_AUTHOR if author else '')).format(
    query=quote(query), author=quote(author))



# ----------------------------------------------------------------------------
# Article
# ----------------------------------------------------------------------------
class Article(FieldSet):
  """
  A concrete Fieldset for scraping article information from a Google Scholar query
  Update this as the Scholar html/css changes

  Attributes
    find_all - a soup expression to parse an Article out of a full response soup
    Field()  - Field instances that describe how each field (title, authors, etc)
               can be parsed out of the context of an Article soup
  """
  find_all      = staticmethod(lambda soup: soup.find(role='main').find_all(class_="gs_r"))
  title         = Field(lambda soup: re.sub(r'\[[A-Z]+\]', '', soup.h3.text))
  authors       = Field(lambda soup: soup.find(class_='gs_a').text.split('-')[0])
  year          = Field(lambda soup: re.search(r'\b\d{4}\b', soup.find(class_='gs_a').text).group(0), type=int)
  num_citations = Field(lambda soup: re.search(r'Cited by ([0-9]+)', soup.text).group(1), type=int)
  num_versions  = Field(lambda soup: re.search(r'All ([0-9]+) versions', soup.text).group(1), type=int)
  pdf_url       = Field(lambda soup: soup.find('a', {'href': re.compile(r'.pdf$')})['href'])
  journal_url   = Field(lambda soup: soup.h3.find('a', {'href': re.compile(r'(?<!pdf)$')})['href'])
  citations_url = Field(lambda soup: URL_ROOT+soup.find('a', text=re.compile(r'Cited by [0-9]+'))['href'])
  versions_url  = Field(lambda soup: URL_ROOT+soup.find('a', text=re.compile(r'All [0-9]+ versions'))['href'])


# ----------------------------------------------------------------------------
# query Google Scholar
# ----------------------------------------------------------------------------
def query(search='', author='', max_results=10, fetcher=None, fieldset=Article):
  """
  query Google Scholar with a search phrase, and optional author

  If making multiple requests, you can supply a fetcher, which stores
  session cookies, otherwise a new fetcher is created with each call.
  """
  fetcher = fetcher if fetcher else Fetcher()
  parser  = Parser()

  url = _format_url(search, author)
  response = fetcher.fetch(url)
  results = parser.parse(response, fieldset, max_results)
  return results


# ----------------------------------------------------------------------------
# Integrity test
# ----------------------------------------------------------------------------
def email_developer(msg, subject='Bugreport for scholar package',
                         from_='bugreport@scholar.hilton.bristow.io'):
  """
  Email the developer with potential bugs (called by test_integrity)
  """
  from subprocess import Popen, PIPE
  from email.mime.text import MIMEText
  to = 'hilton.bristow+scholar@gmail.com'
  msg = MIMEText(msg)
  msg['Subject'] = subject
  msg['From'] = from_
  msg['To'] = to

  with open('mail.txt', 'w') as f:
    f.write(msg.as_string())

  try:
    sendmail = Popen(['/usr/sbin/sendmail', '-t'], stdin=PIPE)
    sendmail.communicate(msg.as_string())
  except:
    pass


_REPORT = (
  '--------------------------------',
  ' Integrity Tests:    {status}   ',
  '--------------------------------',
  '                                ',
  ' Article find_all:   {find_all} ',
  ' Fields:                        ',
  '{fields}                        ',
  '--------------------------------')

_FIELD_REPORT = '   {field:15}   {status}\n'

def test_integrity(email_report=True):
  """
  Test the integrity of the parser
  Used to determine whether the parser may be broken due to a change in
  Google Scholar layout
  """
  # search 'The Lowry Paper'. If we don't get results, something is definitely wrong...
  articles = query(search='Protein measurement with the Folin phenol reagent')

  status = 'PASSED'
  find_all = 'PASSED'
  fields = ''
  if not articles:
    status = 'FAILED'
    fields = _FIELD_REPORT.format(field='NO INFORMATION', status='')
    find_all = 'FAILED'
  else:
    for field in Article.fields():
      default = getattr(Article, field).default
      failed = all([getattr(article, field) == default for article in articles])
      if failed: status = 'FAILED'
      fields += _FIELD_REPORT.format(field=field, status='FAILED*' if failed else 'PASSED')

  report = '\n'.join(_REPORT).format(status=status, find_all=find_all, fields=fields)
  if status == 'FAILED' and email_report:
    pass
    #email_developer(report)

  return AttributeDict({'report': report, 'passed': status == 'PASSED'})


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
  parser.add_argument('-m', '--max_results', help='Maximum results to return', type=int, default=10)
  parser.add_argument('-f', '--file', help='Write the results to file')
  parser.add_argument('-e', '--encoding', help='Output encoding - dict, json, pickle', default='json')
  parser.add_argument('-t', '--test', help='Test the integrity of the parser', action='store_true')
  parser.add_argument('search_terms', nargs='*')

  # parse the named and positional arguments
  args = parser.parse_args()
  search = ' '.join(args.search_terms)

  # check if we're doing an integrity test
  if args.test:
    integrity = test_integrity()
    print(integrity.report)
    exit(not integrity.passed)

  # retrieve the articles
  articles = query(search, args.author, args.max_results)

  # format the articles
  merged = [article.dumps() for article in articles]
  formatted = {
    'dict':   lambda: merged,
    'json':   lambda: json.dumps(merged, indent=2, ensure_ascii=False),
    'pickle': lambda: pickle.dumps(merged),
  }.get(args.encoding, lambda: None)()

  # write the articles to file, or display them
  if args.file:
    with open(args.file, 'w') as f:
      f.write(formatted.encode('utf8'))
  else:
    print(formatted)
