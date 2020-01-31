#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import time
import re
import json
import string
import pandas as pd
import numpy as np
from datetime import datetime as dt
from dateutil.relativedelta import relativedelta as reldelta
from random import randint
from slacktools import SlackTools
from kavalkilu import Keys, Hosts, Amcrest, MySQLLocal, DateTools, \
    WebExtractor, TextCleaner, MarkovText, GSheetReader


help_txt = """
I'm Viktor. Here's what I can do:
*Basic Commands:*
    - `(hello|hi|hey|qq|wyd|greetings)`
    - `speak`
    - `good bot`
    - `[no] (thanks|thank you|tanks)`
    - `time`
    - `access <literally-anything-else>`
    - `sauce` ?????
*Useful commands:*
    - `channel stats`: get a leaderboard of the last 1000 messages posted in the channel
    - `emojis like <regex-pattern>`: get emojis matching the regex pattern
    - `(make sentences|ms) <url1> <url2`: reads in text from the given urls, tries to generate up to 5 sentences
    - `(acro-guess|ag) <acronym> [<group>]`: There are a lot of TLAs at work. This tries to guess what they are.
    - `insult <thing|person> [<group>]`: generates an insult
    - `compliment <thing|person>`: generates something vaguely similar to a compliment
    - `quote me <thing-to-quote>`: turns your phrase into letter emojis
    - `refresh sheets`: Refreshes the GSheet that holds viktor's insults and acronyms
    - `gsheets link`: Shows link to Viktor's GSheet (acronyms, insults, etc..)
    - `show roles`: Shows roles of all the workers of OKR
    - `update dooties [-u @user]`: Updates OKR roles of user (or other user). Useful during a reorg. 
    - `uwu [-l <1 or 2>] <text_to_uwu>`: makes text pwetty (defaults to lvl 2)
"""


class Viktor:
    """Handles messaging to and from Slack API"""

    def __init__(self, log_name, xoxb_token, xoxp_token):
        """
        :param log_name: str, name of the log to retrieve
        :param debug: bool,
        """
        self.bot_name = 'Viktor'
        self.triggers = ['viktor', 'v!']
        self.channel_id = 'alerts'  # #alerts
        # Read in common tools for interacting with Slack's API
        self.st = SlackTools(log_name, triggers=self.triggers, team='orbitalkettlerelay',
                             xoxp_token=xoxp_token, xoxb_token=xoxb_token)
        # Two types of API interaction: bot-level, user-level
        self.bot = self.st.bot
        self.user = self.st.user
        self.bot_id = self.bot.auth_test()['user_id']

        self.approved_users = ['UM35HE6R5', 'UM3E3G72S']
        self.emoji_list = list(self.st.get_emojis().keys())
        self.gs_dict = {}

        self.viktor_sheet = '1KYEbx2Y953u2fIXcntN_xKjBL_6DS02v7y7OcDjv4XU'
        self._read_in_sheets()
        self.roles = self.read_roles()

        self.commands = {
            'garage door status': self.get_garage_status,
            'good bot': 'thanks <@{user}>!',
            'gsheets link': self.show_gsheet_link(),
            'help': help_txt,
            'temps': self.get_temps,
            'sauce': 'ay <@{user}> u got some jokes!',
            'speak': 'woof',
        }

    def handle_command(self, event_dict):
        """Handles a bot command if it's known"""
        # Simple commands that we can map to a function
        response = None
        message = event_dict['message']
        raw_message = event_dict['raw_message']
        user = event_dict['user']
        channel = event_dict['channel']

        if message in self.commands.keys():
            cmd = self.commands[message]
            if callable(cmd):
                # Call the command
                response = cmd()
            else:
                # Response string
                response = cmd
        # elif message == 'garage':
        #     if user not in self.approved_users:
        #         response = self.sarcastic_response()
        #     else:
        #         self.take_garage_pic(channel)
        #         response = 'There ya go!'
        # elif message == 'outdoor':
        #     if user not in self.approved_users:
        #         response = self.sarcastic_response()
        #     else:
        #         self.take_outdoor_pic(channel)
        #         response = 'There ya go!'
        elif message == 'time':
            response = 'The time is {:%F %T}'.format(dt.today())
        elif message == 'uwu that':
            response = self.uwu(self.get_prev_msg_in_channel(event_dict))
        elif message == 'show roles':
            response = 'This is currently `borked`'
            # roles_output = self.show_roles()
            #
            # for role_part in roles_output:
            #     self.st.send_message(channel, f'```{role_part}```')
        elif message == 'channel stats':
            # response = self.get_channel_stats(channel)
            response = 'This request is currently `borked`. I\'ll repair it later.'
        elif message.startswith('make sentences') or message.startswith('ms '):
            response = self.generate_sentences(message)
        elif any([message.startswith(x) for x in ['acro-guess', 'ag']]):
            response = self.guess_acronym(message)
        elif message.startswith('insult'):
            response = self.insult(message)
        elif message.startswith('compliment'):
            response = self.compliment(message, user)
        elif message.startswith('emojis like'):
            response = self.get_emojis_like(message)
        elif message.startswith('uwu'):
            response = self.uwu(raw_message)
        elif any([x in message for x in ['thank you', 'thanks', 'tanks']]):
            response = self.overly_polite(message)
        elif message.startswith('access'):
            response = ''.join([':ah-ah-ah:'] * randint(5, 50))
        elif message.startswith('quote me'):
            msg = message[len('quote me'):].strip()
            response = self.st.build_phrase(msg)
        elif message.startswith('update dooties'):
            response = 'This is currently `borked`'
            # self.update_roles(user, channel, raw_message)
        elif message == 'refresh sheets':
            self._read_in_sheets()
            response = 'Sheets have been refreshed! `{}`'.format(','.join(self.gs_dict.keys()))
        elif any([message.startswith(x) for x in ['hey', 'hello', 'howdy', 'salut', 'hi', 'qq', 'wyd', 'greetings']]):
            response = self.sh_response()
        elif message != '':
            response = "I didn't understand this: `{}`\n " \
                       "Use `v!help` to get a list of my commands.".format(message)

        if response is not None:
            resp_dict = {
                'user': user
            }
            self.st.send_message(channel, response.format(**resp_dict))

    def sarcastic_response(self):
        """Sends back a sarcastic response when user is not allowed to use the action requested"""
        sarcastic_reponses = [
            ''.join([':ah-ah-ah:'] * randint(0, 50)),
            'Lol <@{user}>... here ya go bruv :pick:',
            'Nah boo, we good.',
            'Yeah, how about you go on ahead and, you know, do that yourself.'
            ':bye_felicia:'
        ]

        return sarcastic_reponses[randint(0, len(sarcastic_reponses) - 1)]

    def get_channel_stats(self, channel):
        """Collects posting stats for a given channel"""
        msgs = self.st.get_channel_history(channel, limit=1000)
        results = {}

        for msg in msgs:
            try:
                user = msg['user']
            except KeyError:
                user = msg['bot_id']
            txt_len = len(msg['text'])
            if user in results.keys():
                results[user]['msgs'].append(txt_len)
            else:
                # Apply new dict for new user
                results[user] = {'msgs': [txt_len]}

        # Process messages
        for k, v in results.items():
            results[k] = {
                'total_messages': len(v['msgs']),
                'avg_msg_len': sum(v['msgs']) / len(v['msgs'])
            }

        res_df = pd.DataFrame(results).transpose()

        res_df = res_df.reset_index()
        res_df = res_df.rename(columns={'index': 'user'})
        user_names = pd.DataFrame(self.st.get_users_info(res_df['user'].tolist()))[['id', 'real_name']]
        res_df = res_df.merge(user_names, left_on='user', right_on='id', how='left').drop(['user', 'id'],
                                                                                          axis=1)
        res_df = res_df[['real_name', 'total_messages', 'avg_msg_len']]
        res_df['total_messages'] = res_df['total_messages'].astype(int)
        res_df['avg_msg_len'] = res_df['avg_msg_len'].round(1)
        res_df = res_df.sort_values('total_messages', ascending=False)
        response = '*Stats for this channel:*\n Total messages examined: {}\n' \
                   '```{}```'.format(len(msgs), self.st.df_to_slack_table(res_df))
        return response

    def get_prev_msg_in_channel(self, event_dict):
        """Gets the previous message from the channel"""
        resp = self.bot.conversations_history(
            channel=event_dict['channel'],
            latest=event_dict['ts'],
            limit=10)
        if not resp['ok']:
            return None
        if 'messages' in resp.data.keys():
            msgs = resp['messages']
            return msgs[0]['text']
        return None

    def take_outdoor_pic(self, channel):
        """Takes snapshot of outside, sends to Slack channel"""
        # Take a snapshot of the garage
        garage_cam_ip = Hosts().get_host('ac-v2lis')['ip']
        creds = Keys().get_key('webcam_api')
        cam = Amcrest(garage_cam_ip, creds)
        tempfile = '/tmp/v2lissnap.jpg'
        cam.camera.snapshot(channel=0, path_file=tempfile)
        self.st.upload_file(channel, tempfile, 'v2lis_snapshot_{:%F %T}.jpg'.format(dt.today()))

    def take_garage_pic(self, channel):
        """Takes snapshot of garage, sends to Slack channel"""
        # Take a snapshot of the garage
        garage_cam_ip = Hosts().get_host('ac-garage')['ip']
        creds = Keys().get_key('webcam_api')
        cam = Amcrest(garage_cam_ip, creds)
        tempfile = '/tmp/garagesnap.jpg'
        cam.camera.snapshot(channel=0, path_file=tempfile)
        self.st.upload_file(channel, tempfile, 'garage_snapshot_{:%F %T}.jpg'.format(dt.today()))

    def get_temps(self):
        """Gets device temperatures"""
        eng = MySQLLocal('homeautodb')

        temp_query = """
            SELECT
                l.location
                , temps.record_value AS value
                , temps.record_date
            FROM
                homeautodb.temps
            LEFT JOIN
                homeautodb.locations AS l ON temps.loc_id = l.id
            WHERE
                l.location != 'test'
            ORDER BY
                3 DESC
            LIMIT 100
        """
        temps = pd.read_sql_query(temp_query, eng.connection)

        cur_temps = temps.groupby('location', as_index=False).first()
        today = pd.datetime.today()
        for i, row in cur_temps.iterrows():
            # Determine the trend of last 6 data points
            df = temps[temps.location == row['location']].sort_values('record_date', ascending=True).tail(10)
            # Determine slope of data
            data = df.value[-2:]
            coeffs = np.polyfit(data.index.values, list(data), 1)
            slope = coeffs[-2]
            cur_temps.loc[i, 'trend'] = np.round(slope, 4)

            # Make the recorded date more human readable
            if not pd.isnull(row['record_date']):
                datediff = reldelta(today, pd.to_datetime(row['record_date']))
                datediff = DateTools().human_readable(datediff)
            else:
                datediff = 'unknown'
            cur_temps.loc[i, 'ago'] = datediff

        cur_temps = cur_temps[['location', 'value', 'trend', 'ago']]

        response = '*Most Recent Temperature Readings:*\n```{}```'.format(self.st.df_to_slack_table(cur_temps))
        return response

    def get_garage_status(self):
        """Gets device uptime for specific devices"""
        eng = MySQLLocal('homeautodb')

        garage_status_query = """
            SELECT
                d.name
                , d.status
                , d.status_chg_date
                , d.update_date
            FROM
                doors AS d
            WHERE
                name = 'garage'
        """
        garage_status = pd.read_sql_query(garage_status_query, con=eng.connection)
        status_dict = {k: v[0] for k, v in garage_status.to_dict().items()}
        response = "*Current Status*: `{status}`\n *Changed at*:" \
                   " `{status_chg_date:%F %T}`\n *Updated*: `{update_date:%F %T}`".format(**status_dict)
        return response

    def get_emojis_like(self, message, max_res=500):
        """Gets emojis matching in the system that match a given regex pattern"""

        # Parse the regex from the message
        ptrn = re.search(r'(?<=emojis like ).*', message)
        if ptrn.group(0) != '':
            # We've got a pattern to use
            pattern = re.compile(ptrn.group(0))
            emojis = self.st.get_emojis()
            matches = [k for k, v in emojis.items() if pattern.match(k)]
            len_match = len(matches)
            if len_match > 0:
                # Slack apparently handles message length limitations on its end, so
                #   let's just put all the emojis together into one string
                response = ''.join([':{}:'.format(x) for x in matches[:max_res]])
            else:
                response = 'No results for pattern `{}`'.format(ptrn.group(0))

            if len_match >= max_res:
                # Append to the emoji_str that it was truncated
                trunc_resp = '`**Truncated Results ({}) -> ({})**`'.format(len_match, max_res)
                response = '{}\n{}'.format(trunc_resp, response)
        else:
            response = "I couldn't find a pattern from your message. Get your shit together <@{user}>"
        return response

    def generate_sentences(self, message):
        """Builds a Markov chain from some text sources"""
        # Parse out urls
        msg_split = message.split(' ')
        matches = [x for x in msg_split if re.search(r'http[s]?:\/\/\S+', x) is not None]

        if len(matches) > 0:
            # We've got some urls. Make sure we limit it to 5 in case someone's greedy
            urls = matches[:4]
            we = WebExtractor()
            cleaner = TextCleaner()
            clean_list = []
            for url in urls:
                # Collect HTML elements
                # Slack adds '<' and '>' to the urls. Remove them
                url = re.sub(r'[<>]', '', url)
                elems = we.get_matching_elements(url, ['li', 'p', 'span'])
                # Extract text from tags
                txt_list = []
                for elem in elems:
                    try:
                        elemtxt = elem.get_text()
                        # Try to take out any CSS / javascript that may have gotten in
                        # elemtxt = re.sub(r'(function\s+\w+\(.*\};?|\{.*\})', '', elemtxt)
                        if len(re.sub('[.,\/#!$%\^&\*;:{}=\-`~()]', '', elemtxt).split(' ')) >= 5:
                            txt_list.append(elemtxt)
                    except AttributeError:
                        pass
                cleaned = ''.join([cleaner.process_text(x) for x in txt_list])
                clean_list.append(cleaned)

            mkov = MarkovText(clean_list)
            sentences = []
            for attempt in range(5):
                try:
                    sentences = mkov.generate_n_sentences(5)
                    if len(sentences) > 0:
                        break
                except TypeError:
                    pass

            if len(sentences) > 0:
                # Join them and send them
                return '\n---\n'.join(sentences)
            else:
                return "Hmmm. I wasn't able to make any sense of these urls. I might need a larger text source." \
                       " Also make sure the text falls in either a 'li', 'p' or 'span' element."
        else:
            return "I didn't find a url to use from that text."

    def _read_in_sheets(self):
        """Reads in GSheets for Viktor"""
        gs = GSheetReader(self.viktor_sheet)
        sheets = gs.sheets
        self.gs_dict = {}
        for sheet in sheets:
            self.gs_dict.update({
                sheet.title: gs.get_sheet(sheet.title)
            })

    def sh_response(self):
        """Responds to SHs"""
        resp_df = self.gs_dict['responses']
        responses = resp_df['responses_list'].unique().tolist()
        return responses[randint(0, len(responses) - 1)]

    def guess_acronym(self, message):
        """Tries to guess an acronym from a message"""
        message_split = message.split()
        if len(message_split) <= 1:
            return "I can't work like this! I need a real acronym!!:ragetype:"
        # We can work with this
        acronym = message_split[1]
        if len(message_split) >= 3:
            flag = message_split[2].replace('-', '')
        else:
            flag = 'standard'
        # clean of any punctuation (or non-letters)
        acronym = re.sub(r'\W', '', acronym)

        # Choose the acronym list to use
        acro_df = self.gs_dict['acronyms']
        cols = acro_df.columns.tolist()
        if flag not in cols:
            return 'Cannot find set `{}` in the `acronyms` sheet. ' \
                   'Available sets: `{}`'.format(flag, ','.join(cols))
        words = acro_df.loc[~acro_df[flag].isnull(), flag].unique().tolist()

        # Put the words into a dictionary, classified by first letter
        a2z = string.ascii_lowercase
        word_dict = {k: [] for k in a2z}
        for word in words:
            word = word.replace('\n', '')
            if len(word) > 1:
                word_dict[word[0].lower()].append(word.lower())

        # Build out the real acryonym meaning
        guesses = []
        for guess in range(3):
            meaning = []
            for letter in list(acronym):
                if letter.isalpha():
                    word_list = word_dict[letter]
                    meaning.append(word_list[randint(0, len(word_list) - 1)])
                else:
                    meaning.append(letter)
            guesses.append(' '.join(list(map(str.title, meaning))))

        return ':robot-face: Here are my guesses for *{}*!\n {}'.format(acronym.upper(),
                                                                        '\n_OR_\n'.join(guesses))

    def insult(self, message):
        """Insults the user at their request"""
        message_split = message.split()
        if len(message_split) <= 1:
            return "I can't work like this! I need something to insult!!:ragetype:"

        # We can work with this
        flag = message_split[-1]
        if '-' in flag:
            flag = flag.replace('-', '')
            # Skip the last part of the message, as that's the flag
            target = ' '.join(message_split[1:-1])
        else:
            flag = 'standard'
            # Get the rest of the message
            target = ' '.join(message_split[1:])

        # Choose the acronym list to use
        insult_df = self.gs_dict['insults']
        cols = insult_df.columns.tolist()
        # Parse the columns into flags and order
        flag_dict = {}
        for col in cols:
            if '_' in col:
                k, v = col.split('_')
                if k in flag_dict.keys():
                    flag_dict[k].append(col)
                else:
                    flag_dict[k] = [col]

        if flag not in flag_dict.keys():
            return 'Cannot find set `{}` in the `insults` sheet. ' \
                   'Available sets: `{}`'.format(flag, ','.join(flag_dict.keys()))
        insults = []
        for insult_part in sorted(flag_dict[flag]):
            part_series = insult_df[insult_part].replace('', np.NaN).dropna().unique()
            part = part_series.tolist()
            insults.append(part[randint(0, len(part) - 1)])

        if target == 'me':
            return "You aint nothin but a {}".format(' '.join(insults))
        else:
            return "{} aint nothin but a {}".format(target, ' '.join(insults))

    def compliment(self, message, user):
        """Insults the user at their request"""
        message_split = message.split()
        if len(message_split) <= 1:
            return "I can't work like this! I need something to compliment!!:ragetype:"

        # We can work with this
        flag = message_split[-1]
        if '-' in flag:
            flag = flag.replace('-', '')
            # Skip the last part of the message, as that's the flag
            target = ' '.join(message_split[1:-1])
        else:
            flag = 'std'
            # Get the rest of the message
            target = ' '.join(message_split[1:])

        # Choose the acronym list to use
        compliment_df = self.gs_dict['compliments']
        cols = compliment_df.columns.tolist()
        # Parse the columns into flags and order
        flag_dict = {}
        for col in cols:
            if '_' in col:
                k, v = col.split('_')
                if k in flag_dict.keys():
                    flag_dict[k].append(col)
                else:
                    flag_dict[k] = [col]

        if flag not in flag_dict.keys():
            return 'Cannot find set `{}` in the `compliments` sheet. ' \
                   'Available sets: `{}`'.format(flag, ','.join(flag_dict.keys()))
        compliments = []
        for compliment_part in sorted(flag_dict[flag]):
            part_series = compliment_df[compliment_part].replace('', np.NaN).dropna().unique()
            part = part_series.tolist()
            compliments.append(part[randint(0, len(part) - 1)])

        if target == 'me':
            return "{} Viktor.".format(' '.join(compliments))
        else:
            return "Dear {}, {} <@{}>.".format(target, ' '.join(compliments), user)

    def overly_polite(self, message):
        """Responds to 'no, thank you' with an extra 'no' """
        # Count the 'no's
        no_cnt = message.count('no')
        no_cnt += 1
        response = '{}, thank you!'.format(', '.join(['no'] * no_cnt)).capitalize()
        return response

    def message_grp(self, message):
        """Wrapper to send message to whole channel"""
        self.st.send_message(self.channel_id, message)

    def show_roles(self):
        """Prints users roles to channel"""
        roles_output = ['OKR Roles (as of last reorg):', '-' * 40]

        users = self.st.get_channel_members('CM3E3E82J')
        user_dict = {x['id']: x['name'] for x in users}

        for user in users:
            if user in self.roles['user'].tolist():
                self.roles.loc[self.roles['user'] == user, 'name'] = user_dict[user]

        roles_output.append(self.st.df_to_slack_table(self.roles[['name', 'role']]))

        return roles_output

    def get_user_by_id(self, user_id, user_list):
        """Returns a dictionary of player info that has a matching 'id' value in a list of player dicts"""
        user_idx = self.get_user_index_by_id(user_id, user_list)
        return user_list[user_idx]

    def get_user_index_by_id(self, user_id, user_list):
        """Returns the index of a player in a list of players that has a matching 'id' value"""
        return user_list.index([x for x in user_list if x['id'] == user_id][0])

    def read_roles(self):
        """Reads in JSON of roles"""
        return self.gs_dict['okr_roles']

    def write_roles(self):
        """Writes roles to GSheeets"""
        self.st.write_sheet(self.viktor_sheet, 'okr_roles', self.roles)

    def update_roles(self, user, channel, msg):
        """Updates a user with their role"""
        content = msg[len('update dooties'):].strip()
        if '-u' in content:
            # Updating role of other user
            # Extract user
            user = content.split()[1].replace('<@', '').replace('>', '').upper()
            content = ' '.join(content.split()[2:])
        self.roles.loc[self.roles['user'] == user, 'role'] = content
        self.st.send_message(channel, 'Role for <@{}> updated.'.format(user))
        # Save roles to Gsheet
        self.write_roles()

    def show_gsheet_link(self):
        """Prints a link to the gsheet in the channel"""

        return f'https://docs.google.com/spreadsheets/d/{self.viktor_sheet}/'

    def uwu(self, msg):
        """uwu-fy a message"""
        default_lvl = 2

        if '-l' in msg.split():
            level = msg.split()[msg.split().index('-l') + 1]
            level = int(level) if level.isnumeric() else default_lvl
            text = ' '.join(msg.split()[msg.split().index('-l') + 2:])
        else:
            level = default_lvl
            text = msg.replace('uwu', '').strip()

        chars = [
            '(=｀ω´=)','( =｀ェ´=)','（=´∇｀=）',' (=´∇｀=)',
            '( = ^ ◡ ^= )','(= ^ -ω- ^=)', '(＾º◡º＾❁)',' (^ ≗ω≗ ^)',
            '三三ᕕ( ᐛ )ᕗ',' ＼＼\(۶ ᐛ )۶//／／', ' ᕦ( ᐛ )ᕤ',
            'SMOOO━━(´з(ε｀)━━OOCH★☆', '(〃´∀｀〃)ε｀●)chu♪',
            '(ʃƪ ˘ ³˘)♥(˘ ε˘ʃƪ)', ' ┐(°益°)┌'
        ]

        if level >= 1:
            # Level 1: Letter replacement
            text = text.translate(str.maketrans('rRlL', 'wWwW'))

        if level >= 2:
            # Level 2: Placement of 'uwu' when certain patterns occur

            pattern_whitelist = {
                'uwu': {
                    'start': 'u',
                    'anywhere': ['nu', 'ou', 'du'],
                },
                'owo': {
                    'start': 'o',
                    'anywhere': ['ow', 'bo', 'do', 'on'],
                }
            }
            # Rebuild the phrase letter by letter
            phrase = []
            for word in text.split(' '):
                for pattern, pattern_dict in pattern_whitelist.items():
                    if word.startswith(pattern_dict['start']):
                        word = word.replace(pattern_dict['start'], pattern)
                    else:
                        for fragment in pattern_dict['anywhere']:
                            if fragment in word:
                                word = word.replace(pattern_dict['start'], pattern)
                phrase.append(word)
            text = ' '.join(phrase)

            # Last step, insert random characters
            text = chars[np.random.choice(len(chars), 1)[0]] + text + chars[np.random.choice(len(chars), 1)[0]]

        return text
