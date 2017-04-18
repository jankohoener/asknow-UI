# -*- coding: utf-8 -*-
# Copyright 2016 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


#import webapp2
import json
from google.appengine.api import memcache, urlfetch
import logging
from handlerlib import *
from datatypes import *
from userauth import *
import urllib, urllib2
from urllib2 import Request
import os
		
class AskNowDemoHandler(Handler):
	def render_page(self, template, loggedin = False):
		self.render(template, loggedin = loggedin)
	
	def retrieve_answers(self, q):
		params = { 'q': q.encode('utf-8') }
		cur_answer = {}
		logging.info('Retrieving answers for question "%s" from AskNow' % q)
		#url = 'https://jankos-project.appspot.com/asknow/json?q=%s' % q # urllib.urlencode() doesn't work with UTF-8 characters!
		url = 'https://jankos-project.appspot.com/asknow/json?%s' % urllib.urlencode(params)
		result = urlfetch.fetch(url)
		if result.status_code == 200:
			logging.info('Retrieved answers for question "%s" from AskNow, proceeding.' % q)
			cur_answer = json.loads(result.content)
			return cur_answer
		else: # FIXME: better error handling
			return None

	def get(self):
		logging.info('Start building demo page')
		q = self.request.get('q')
		self.response.headers['Content-Type'] = 'text/html; charset=UTF-8'
		auth = True
		cookie_data = self.request.cookies.get('userid')
		if cookie_data:
			logging.info('Cookie for userid is set, reading.')
			cookie_data_split = cookie_data.split('|')
			if len(cookie_data_split) == 2:
				logging.info('Cookie split at |, checking hash.')
				userkeystr = cookie_data_split[0]
				userhash = cookie_data_split[1]
				if self.hash_str(userkeystr) == userhash:
					auth = True
					logging.info('Authentification successful, retrieving user for id %s' % userkeystr)
					key = 'user-%s' % userkeystr
					user = memcache.get(key)
					if user:
						logging.info('User retrieved from cache.')
					else:
						logging.info('User not found in cache, retrieving from database.')
						userkey = int(userkeystr)
						user = AskNowUser.get_by_id(userkey)
						logging.info('User retrieved from database')
						memcache.set(key, user)
					userdbkey = user.key
					username = user.username	 
				else:
					logging.info('Authentification not successful, resetting cookie and continuing as anonymous user')
					self.reset_cookie('userid')
					auth = False
			else:
				logging.info('Cookie for userid misformatted, resetting cookie and continuing as anonymous user')
				self.reset_cookie('userid')
				auth = False
		else:
			logging.info('Cookie for userid not set, continuing as anonymous user')
			auth = False
		if not auth and not q:
			logging.info('User not authentificated and no question asked, showing plain demo page.')
			self.render('asknowdemo.html', loggedin = auth)
			return
		if not auth and q:
			logging.info('Anonymous user asked question %s, loading answer' % q)
			answerslist = []
			answerslist.append(self.retrieve_answers(q))
			logging.info('Answers loaded, rendering.')
			self.render('asknowdemo_answer.html', answerslist = answerslist, q = q, loggedin = auth)
			return
		# if auth:
		qkey = 'questions-%s' % username
		logging.info('User authentificated, loading former questions from cache.')
		cache = memcache.get(qkey)
		if cache:
			logging.info('Questions found in cache, loading answers')
			questions = cache
		else:
			logging.info('Questions not found in cache, loading from database')
			query = AskNowQuestion.query(AskNowQuestion.userid == userdbkey, distinct=True, projection=[AskNowQuestion.asked, AskNowQuestion.question]).order(-AskNowQuestion.asked)
			query = list(query)
			questions = []
			for res in query:
				questions.append(res.question)
			logging.info('Questions loaded from database.')
		if q:
			questions.insert(0, q)
			new_question = AskNowQuestion(userid = userdbkey, question = q)
			new_question.put()
			logging.info('New question added to list and to database.')
		display_questions = questions[:5]
		memcache.set(qkey, display_questions)
		logging.info('5 most recent questions added to cache, loading answers for questions.')
		answerslist = []
		error = ''
		message = ''
		for question in display_questions:
			cur_answers = self.retrieve_answers(question)
			if cur_answers and not cur_answers.get('error'):
				answerslist.append(cur_answers)
				logging.info('Retrieved answers for question "%s"' % question)
			elif cur_answers and cur_answer.error and question == q:
				error = cur_answer.error
				message = cur_answer.message
		logging.info('Rendering answer page.')
		self.render('asknowdemo_answer.html', answerslist = answerslist, q = q, error = error, message = message, loggedin = auth)
			
class AskNowJSONAnswerHandler(Handler):
	API_URL = 'https://en.wikipedia.org/w/api.php'
	DBPEDIASL_URL = 'http://model.dbpedia-spotlight.org/en/annotate'
	DBPEDIASL_CONF = 0.75

	def retrieve_info(self, titles):
		answers = {}
		answers['information'] = []
		answers['titles'] = []
		req = {}
		answer = {}
		req['action'] = 'query'
		req['prop'] = 'info|pageimages|extracts'
		req['titles'] = '|'.join(titles)
		req['inprop'] = 'url'
		req['piprop'] = 'original'
		req['exintro'] = True
		req['exsectionformat'] = 'raw'
		req['format'] = 'json'
		req['indexpageids'] = True
		req['redirects'] = True
		while True:
			params = urllib.urlencode(req)
			url = self.API_URL + '?' + params
			urlobj = urlfetch.fetch(url)
			json_data = json.loads(urlobj.content)
			if json_data.get('error'):
				answer['error'] = 3
				answer['message'] = 'Error parsing Wikipedia API: %s' % json_data['error']['info']
				answers['information'].append(answer)
				continue
			pageids = json_data['query']['pageids']
			for pageid, info in json_data['query']['pages'].items():
				if not answer.get(pageid):
					answer[pageid] = {}
				if info.get('title'):
					answer[pageid]['title'] = info['title']
					if info['title'] not in answers['titles']:
						answers['titles'].append(info['title'])
				if info.get('extract'):
					answer[pageid]['abstract'] = info['extract']
				if info.get('fullurl'):
					answer[pageid]['wplink'] = info['fullurl']
				if info.get('thumbnail'):
					answer[pageid]['imgsrc'] = info['thumbnail']['original']
			if json_data.get('continue'):
				req.update(json_data['continue'])
			if json_data.get('batchcomplete') == '':
				break
		answers['information'] = answer.values()
		answers['count'] = len(answers['information'])
		return answers
	
	
	"""
	Returns an object that contains the 
	
	
	"""
	def get(self):
		known_answers = {
			'who is the president of the united states': ['Barack Obama'],
			'how many goals did gerd müller score': ['Gerd Müller'],
			'who is the president elect of the united states': ['Donald Trump'],
			'in which city was beethoven born': ['Bonn'],
			'in which city was adenauer born': ['Cologne'],
			'what country is shah rukh khan from': ['India'],
			'what are the capitals of germany and india': ['Berlin', 'New Delhi'],
			'what are the capitals of germany, india and usa': ['Berlin', 'New Delhi', 'Washington D.C.'],
			'what are the capitals of germany, india, usa and france': ['Berlin', 'New Delhi', 'Washington D.C.', 'Paris']
		}
		query = self.request.get('q')
		question = self.request.get('q')
		question = question.lower().replace('?', '')
		question = question.encode('utf-8')
		answers = {}
		if not question:
			answers = { 'error': 2, 'message': 'Application needs a q parameter, none given.' }
		elif question in known_answers:
			answers = self.retrieve_info(known_answers[question])
			answers['answered'] = True
		else:
			param = {}
			param['text'] = question
			param['confidence'] = self.DBPEDIASL_CONF
			params = 'text=%s&confidence=%s' % (param['text'], param['confidence'])
			url = self.DBPEDIASL_URL + '?' + urllib.urlencode(param)
			headers = { 'Accept' : 'application/json' }
			a = urlfetch.fetch(url, headers = headers)
			if a.status_code == 200:
				entityobj = json.loads(a.content)
				if entityobj.get('Resources'):
					titles = []
					for entity in entityobj['Resources']:
						if entity.get('@URI'):
							title = os.path.basename(entity['@URI']).encode('utf-8')
							titles.append(title)
					if titles:
						answers = self.retrieve_info(titles)
						answers['answered'] = False
		answers['question'] = query
		json_string = json.dumps(answers)
		self.response.headers['Content-Type'] = 'application/json; charset=UTF-8'
		self.write(json_string)
		

PATH = '/asknow/'
app = webapp2.WSGIApplication([
    webapp2.Route(PATH + 'demo', handler = AskNowDemoHandler, name = 'demo'),
    (PATH + 'json', AskNowJSONAnswerHandler),
    (PATH + 'signup', AskNowSignUpHandler),
    (PATH + 'login', AskNowLoginHandler),
    (PATH + 'logout', AskNowLogoutHandler),
], debug=True)