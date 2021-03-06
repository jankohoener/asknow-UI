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


from userauth import *
from api import *
from demo import *

ASKNOW_PATH = '/asknow/'
app = webapp2.WSGIApplication([
		webapp2.Route(ASKNOW_PATH + 'demo', handler = AskNowDemoHandler, name = 'demo'),
		(ASKNOW_PATH + 'json', AskNowJSONAnswerHandler),
		(ASKNOW_PATH + 'signup', AskNowSignUpHandler),
		(ASKNOW_PATH + 'login', AskNowLoginHandler),
		(ASKNOW_PATH + 'logout', AskNowLogoutHandler),
], debug=True)
