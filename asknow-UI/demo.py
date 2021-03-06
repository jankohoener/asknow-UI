# -*- coding: utf-8 -*-
# Copyright 2017 Janko Hoener
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


import json
from google.appengine.api import memcache, urlfetch
import logging
from handlerlib import *
from datatypes import *
from userauth import *
import urllib, urllib2
from urllib2 import Request
import os, sys
from google.appengine.api.urlfetch_errors import *

class AskNowDemoHandler(Handler):
	ASKNOW_URL = 'https://jankos-project.appspot.com/asknow/json' # FIXME: use real AskNow
	DEMO_URL = 'demo.html'
	ANSWER_URL = 'demo_answer.html'
	
	def render_page(self, template, loggedin = ''):
		self.render(template, loggedin = loggedin)
	
	def retrieve_answers(self, q):
		params = { 'q': q.encode('utf-8') }
		cur_answer = {}
		logging.info('Retrieving answers for question "%s" from AskNow' % q)
		url = self.ASKNOW_URL + '?%s' % urllib.urlencode(params)
		retry = 2
		while retry:
			try:
				result = urlfetch.fetch(url)
			except:
				retry = retry - 1
				if not retry:
					exc_type, exc_value, exc_traceback = sys.exc_info()
					logging.debug(exc_value)
					cur_answer['status'] = 2
					cur_answer['message'] = 'Cannot reach AskNow API.'
					cur_answer['leninfo'] = 0
					cur_answer['lentitles'] = 0
					cur_answer['question'] = q
					cur_answer['answered'] = False
					return cur_answer
			else:
				if result.status_code == 200:
					logging.info('Retrieved answers for question "%s" from AskNow, proceeding.' % q)
					cur_answer = json.loads(result.content)
					cur_answer['status'] = 0
					cur_answer['message'] = 'Answer successfully retrieved from AskNow'
				else:
					cur_answer['status'] = 4
					cur_answer['message'] = 'Retrieved status code != 200 from AskNow'
					cur_answer['leninfo'] = 0
					cur_answer['lentitles'] = 0
					cur_answer['question'] = q
					cur_answer['answered'] = False
				return cur_answer

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
			self.render(self.DEMO_URL)
			return
		if not auth and q:
			logging.info('Anonymous user asked question %s, loading answer' % q)
			answerslist = []
			answerslist.append(self.retrieve_answers(q))
			logging.info('Answers loaded, rendering.')
			self.render(self.ANSWER_URL, answerslist = answerslist, q = q)
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
			if cur_answers:
				answerslist.append(cur_answers)
				logging.info('Retrieved answers for question "%s"' % question)
		logging.info('Rendering answer page.')
		self.render(self.ANSWER_URL, answerslist = answerslist, q = q, error = error, message = message, loggedin = username)