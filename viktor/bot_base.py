#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
import string
import sys
import requests
from datetime import datetime
from typing import List, Optional, Union, Dict
import pandas as pd
import numpy as np
from sqlalchemy.orm import Session
from datetime import datetime as dt
from random import randint, choice
from slacktools import SlackBotBase, BlockKitBuilder as bkb
from easylogger import Log
import viktor.app as vik_app
from .linguistics import Linguistics
from .phrases import PhraseBuilders
from .settings import auto_config
from .model import TableUsers, TableEmojis, TablePerks, TableUwu, TableResponses
from .forms import Forms


class Viktor:
    """Handles messaging to and from Slack API"""

    def __init__(self, parent_log: Log, session: Session):
        """
        Args:

        """
        self.bot_name = f'{auto_config.BOT_FIRST_NAME} {auto_config.BOT_LAST_NAME}'
        self.log = Log(parent_log, child_name='viktor_bot')
        self.triggers = auto_config.TRIGGERS
        self.test_channel = auto_config.TEST_CHANNEL
        self.emoji_channel = auto_config.EMOJI_CHANNEL
        self.general_channel = auto_config.GENERAL_CHANNEL
        self.approved_users = auto_config.ADMINS
        self.version = auto_config.VERSION
        self.update_date = auto_config.UPDATE_DATE
        # create a session
        self.session = session

        self.ling = Linguistics()

        # Begin loading and organizing commands
        # Command categories
        cat_basic = 'basic'
        cat_useful = 'useful'
        cat_notsouseful = 'not so useful'
        cat_org = 'org'
        cat_lang = 'language'
        cmd_categories = [cat_basic, cat_useful, cat_notsouseful, cat_lang, cat_org]
        self.commands = {
            r'^help': {
                'pattern': 'help',
                'cat': cat_basic,
                'desc': 'Description of all the commands I respond to!',
                'response': [],
            },
            r'^about$': {
                'pattern': 'about',
                'cat': cat_useful,
                'desc': 'Bootup time of Viktor\'s current instance, his version and last update date',
                'response': [self.get_bootup_msg],
            },
            r'^m(ain\s?menu|m)': {
                'pattern': 'main menu|mm',
                'cat': cat_basic,
                'desc': 'Wiktor main menu',
                'response': [self.prebuild_main_menu, 'user', 'channel'],
            },
            r'^add emoji': {
                'pattern': 'add emoji',
                'cat': cat_useful,
                'desc': 'Begins emoji upload process',
                'response': [self.add_emoji_form_p1, 'user', 'channel'],
            },
            r'good bo[tiy]': {
                'pattern': 'good bo[tiy]',
                'cat': cat_basic,
                'desc': 'Did I do something right for once?',
                'response': 'thanks <@{user}>!',
            },
            r'^(gsheet[s]?|show) link$': {
                'pattern': '(gsheets|show) link',
                'cat': cat_useful,
                'desc': 'Shows link to Viktor\'s GSheet (acronyms, insults, etc..)',
                'response': self.show_gsheets_link,
            },
            r'^time$': {
                'pattern': 'time',
                'cat': cat_basic,
                'desc': 'Display current server time',
                'response': [self.get_time],
            },
            r'^sauce$': {
                'pattern': 'sauce',
                'cat': cat_basic,
                'desc': 'Handle some ridicule...',
                'response': 'ay <@{user}> u got some jokes!',
            },
            r'^speak$': {
                'pattern': 'speak',
                'cat': cat_basic,
                'desc': '_Really_ basic response here.',
                'response': 'woof',
            },
            r'^translate that': {
                'pattern': 'translate that <target_lang_code>',
                'cat': cat_lang,
                'desc': 'Translate the text immediately above this command.',
                'response': [self.translate_that, 'channel', 'ts', 'message', 'match_pattern'],
            },
            r'^translate (in)?to': {
                'pattern': 'translate to <target_lang_code>',
                'cat': cat_lang,
                'desc': 'Translates the text to the target language',
                'response': [self.translate_anything, 'message', 'match_pattern'],
            },
            r'^uwu that$': {
                'pattern': 'uwu that',
                'cat': cat_notsouseful,
                'desc': 'Uwu the text immediately above this command.',
                'response': [self.uwu_that, 'channel', 'ts'],
            },
            r'^show (roles|doo[td]ies)$': {
                'pattern': 'show (roles|doo[td]ies)',
                'cat': cat_org,
                'desc': 'Shows current roles of all the wonderful workers of OKR',
                'response': [self.build_role_txt, 'channel'],
            },
            r'^update doo[td]ies': {
                'pattern': 'update dooties [-u @user]',
                'cat': cat_org,
                'desc': 'Updates OKR roles of user (or other user). Useful during a quick reorg. '
                        '\n\t\t\t_NOTE: You only have to tag a user if it\'s not you._',
                'response': [self.update_roles, 'user', 'channel', 'raw_message', 'match_pattern'],
            },
            r'^show my (role|doo[td]ie)$': {
                'pattern': 'show my (role|doo[td]ie)',
                'cat': cat_org,
                'desc': 'Shows your current role as of the last reorg.',
                'response': [self.build_role_txt, 'channel', 'user'],
            },
            r'^channel stats$': {
                'pattern': 'channel stats',
                'cat': cat_useful,
                'desc': 'Get a leaderboard of the last 1000 messages posted in the channel',
                'response': [self.get_channel_stats, 'channel'],
            },
            r'^(ag|acro[-]?guess)': {
                'pattern': '(acro-guess|ag) <acronym> [-(group|g) <group>, -n <guess-n-times>]',
                'cat': cat_notsouseful,
                'desc': 'There are RBNs of TLAs at OKR. This tries RRRRH to guess WTF they mean IRL. '
                        '\n\t\t\tThe optional group name corresponds to the column name '
                        'of the acronyms in Viktor\'s spreadsheet',
                'response': [self.guess_acronym, 'message'],
            },
            r'^ins[ul]{2}t': {
                'pattern': 'insult <me|thing|person> [-(group|g) <group>]',
                'cat': cat_notsouseful,
                'desc': 'Generates an insult. The optional group name corresponds to the column name '
                        'of the insults in Viktor\'s spreadsheet',
                'response': [self.insult, 'message'],
            },
            r'^phrases?': {
                'pattern': 'phrase(s) [-(group|g) <group>, -n <number-of-cycles>]',
                'cat': cat_notsouseful,
                'desc': 'Generates an phrase from a collection of words. The optional group name '
                        'corresponds to the cluster of column names in the "phrases" tab '
                        'in Viktor\'s spreadsheet',
                'response': [self.phrase_generator, 'message'],
            },
            r'^compliment': {
                'pattern': 'compliment <thing|person> [-(group|g) <group>]',
                'cat': cat_notsouseful,
                'desc': 'Generates a :q:compliment:q:. The optional group name corresponds to the column name '
                        'of the compliments in Viktor\'s spreadsheet',
                'response': [self.compliment, 'raw_message', 'user'],
            },
            r'^facts?': {
                'pattern': 'facts',
                'cat': cat_notsouseful,
                'desc': 'Generates a fact',
                'response': [self.facts],
            },
            r'^emoji[s]? like': {
                'pattern': 'emoji[s] like <regex-pattern>',
                'cat': cat_useful,
                'desc': 'Get emojis matching the regex pattern',
                'response': [self.get_emojis_like, 'match_pattern', 'message'],
            },
            r'^refresh emojis$': {
                'pattern': 'refresh emojis',
                'cat': cat_useful,
                'desc': 'Makes Viktor aware of emojis that have been uploaded since his last reboot.',
                'response': [self.refresh_emojis],
            },
            r'^uwu': {
                'pattern': 'uwu [-l <1 or 2>] <text_to_uwu>',
                'cat': cat_notsouseful,
                'desc': 'Makes text pwettiew and easiew to uwundewstand (defaults to highest uwu level)',
                'response': [self.uwu, 'raw_message'],
            },
            r'(thanks|(no\s?)*\s(t[h]?ank\s?(you|u)))': {
                'cat': cat_basic,
                'desc': 'Thank Viktor for something',
                'response': [self.overly_polite, 'message'],
            },
            r'^emoji my words': {
                'cat': cat_basic,
                'desc': 'Turn your words into emoji',
                'response': [self.word_emoji, 'message', 'match_pattern'],
            },
            r'^((button|btn)\s?game|bg)': {
                'pattern': 'button game',
                'cat': cat_notsouseful,
                'desc': 'Play a game, win (or lose) LTITs',
                'response': [self.button_game],
            },
            r'^access': {
                'pattern': 'access <literally-anything-else>',
                'cat': cat_notsouseful,
                'desc': 'Try to gain access to something - whether that be the power grid to your failing '
                        'theme park on an island off the coast of Costa Rica or something less pressing.',
                'response': [self.access_something],
            },
            r'^quote me': {
                'pattern': 'quote me <thing-to-quote>',
                'cat': cat_notsouseful,
                'desc': 'Turns your quote into letter emojis',
                'response': [self.quote_me, 'message', 'match_pattern'],
            },
            r'^(he(y|llo)|howdy|salu|hi|qq|wyd|greet|servus|ter|bonj)': {
                'cat': cat_notsouseful,
                'desc': 'Responds appropriately to a simple greeting',
                'response': [self.sh_response],
            },
            r'.*inspir.*': {
                'pattern': '<any text with "inspir" in it>',
                'cat': cat_notsouseful,
                'desc': 'Uploads an inspirational picture',
                'response': [self.inspirational, 'channel'],
            },
            r'.*tihi.*': {
                'pattern': '<any text with "tihi" in it>',
                'cat': cat_notsouseful,
                'desc': 'Giggles',
                'response': [self.giggle],
            },
            r'^shurg': {
                'pattern': '<any text with "shurg" at the beginning>',
                'cat': cat_notsouseful,
                'desc': '¯\_(ツ)_/¯',
                'response': [self.shurg, 'message'],
            },
            r'^(randcap|mock)': {
                'pattern': '<any text with "randcap" or "mock" at the beginning>',
                'cat': cat_notsouseful,
                'desc': 'whaT dO yOu thiNK iT Does',
                'response': [self.randcap, 'message'],
            },
            r'^onbo[a]?r[d]?ing$': {
                'pattern': '(onboarding|onboring)',
                'cat': cat_org,
                'desc': 'Prints out all the material needed to get a new OKR employee up to speed!',
                'response': [self.onboarding_docs],
            },
            r'^(update\s?level|level\s?up)': {
                'pattern': '(update level|level up) -u <user>',
                'cat': cat_org,
                'desc': 'Accesses an employee\'s LevelUp registry and increments their level',
                'response': [self.update_user_level, 'channel', 'user', 'message', 'match_pattern']
            },
            r'^ltits': {
                'pattern': 'ltits -u <user> <number>',
                'cat': cat_org,
                'desc': 'Distribute or withdraw LTITs from an employee\'s account',
                'response': [self.update_user_ltips, 'channel', 'user', 'message', 'match_pattern']
            },
            r'^show (my )?perk[s]?': {
                'pattern': 'show [my] perk(s)',
                'cat': cat_org,
                'desc': 'Shows the perks an employee has access to at their current level',
                'response': [self.show_my_perks, 'user']
            },
            r'^show all perks': {
                'pattern': 'show all perks',
                'cat': cat_org,
                'desc': 'Shows all perks currently available at OKR',
                'response': [self.show_all_perks]
            },
            r'^e[nt]\s': {
                'pattern': '(et|en) <word-to-translate>',
                'cat': cat_lang,
                'desc': 'Offers a translation of an Estonian word into English or vice-versa',
                'response': [self.ling.prep_message_for_translation, 'message', 'match_pattern']
            },
            r'^ekss\s': {
                'pattern': 'ekss <word-to-lookup>',
                'cat': cat_lang,
                'desc': 'Offers example usage of the given Estonian word',
                'response': [self.ling.prep_message_for_examples, 'message', 'match_pattern']
            },
            r'^lemma\s': {
                'pattern': 'lemma <word-to-lookup>',
                'cat': cat_lang,
                'desc': 'Determines the lemma of the Estonian word',
                'response': [self.ling.prep_message_for_root, 'message', 'match_pattern']
            },
            r'^wfh\s?(time|epoch)': {
                'pattern': 'wfh (time|epoch)',
                'cat': cat_useful,
                'desc': 'Prints the current WFH epoch time',
                'response': [self.wfh_epoch]
            },
            r'^ety\s': {
                'pattern': 'ety <word>',
                'cat': cat_useful,
                'desc': 'Gets the etymology of a given word',
                'response': [self.ling.get_etymology, 'message', 'match_pattern']
            }
        }

        # Initate the bot, which comes with common tools for interacting with Slack's API
        self.st = SlackBotBase(triggers=self.triggers, credstore=vik_app.credstore,
                               test_channel=self.test_channel, commands=self.commands,
                               cmd_categories=cmd_categories, slack_cred_name=auto_config.BOT_NICKNAME,
                               parent_log=self.log, use_session=True)
        self.bot_id = self.st.bot_id
        self.user_id = self.st.user_id
        self.bot = self.st.bot
        self.generate_intro()

        self.pb = PhraseBuilders(self.st)

        self.st.message_test_channel(blocks=self.get_bootup_msg())

        self.emoji_list = self.refresh_emojis()
        # Place to temporarily store things. Typical structure is activity -> user -> data
        self.state_store = {
            'new-emoji': {}
        }

        self.log.debug(f'{self.bot_name} booted up!')

    def get_bootup_msg(self) -> List[Dict]:
        return [bkb.make_context_section([
            bkb.markdown_section(f"*{self.bot_name}* *`{self.version}`* booted up at `{datetime.now():%F %T}`!"),
            bkb.markdown_section(f"(updated {self.update_date})")
        ])]

    def generate_intro(self):
        """Generates the intro message and feeds it in to the 'help' command"""
        intro = f"Здравствуйте! I'm *{self.bot_name}* (:Q::regional_indicator_v::Q: for short).\n" \
                f"I can help do stuff for you, but you'll need to call my attention first with " \
                f"*`{'`* or *`'.join(self.triggers)}`*\n Example: *`v! hello`*\nHere's what I can do:"
        avi_url = "https://ca.slack-edge.com/TM1A69HCM-ULV018W73-1a94c7650d97-512"
        avi_alt = 'hewwo'
        # Build the help text based on the commands above and insert back into the commands dict
        self.commands[r'^help']['response'] = self.st.build_help_block(intro, avi_url, avi_alt)
        # Update the command dict in SlackBotBase
        self.st.update_commands(self.commands)

    def cleanup(self, *args):
        """Runs just before instance is destroyed"""
        notify_block = [
            bkb.make_context_section([
                bkb.markdown_section(f'{self.bot_name} died. :death-drops::party-dead::death-drops:')
            ])
        ]
        self.st.message_test_channel(blocks=notify_block)
        self.log.info('Bot shutting down...')
        self.log.close()
        sys.exit(0)

    def process_slash_command(self, event_dict: Dict, session: Session):
        """Hands off the slash command processing while also refeshing the session"""
        self.session = session
        self.st.parse_slash_command(event_dict)

    def process_event(self, event_dict: Dict, session: Session):
        """Hands off the event data while also refreshing the session"""
        self.session = session
        self.st.parse_event(event_data=event_dict)

    def process_incoming_action(self, user: str, channel: str, action_dict: Dict, event_dict: Dict,
                                session: Session) -> Optional:
        """Handles an incoming action (e.g., when a button is clicked)"""
        self.session = session
        action_id = action_dict.get('action_id')
        action_value = action_dict.get('value')

        if 'buttongame' in action_id:
            # Button game stuff
            game_value = action_value.split('-')[1]
            if game_value.isnumeric():
                game_value = int(game_value) - 500
                resp = self.update_user_ltips(channel, self.approved_users[0], f'-u <@{user}> {game_value}')
                if resp is not None:
                    self.st.send_message(channel, resp)
        elif action_id == 'new-emoji-p1':
            # Store this user's first portion of the new emoji request
            new_emoji_req = {user: {'url': action_value}}
            self.state_store['new-emoji'].update(new_emoji_req)
            # Send the second portion
            self.add_emoji_form_p2(user=user, channel=channel, url=action_value)
        elif action_id == 'new-emoji-p2':
            # Compile all the details together and try to get the emoji uploaded
            url = self.state_store['new-emoji'].get(user).get('url')
            self.add_emoji(user, channel, url=url, new_name=action_value)

    def prebuild_main_menu(self, user_id: str, channel: str):
        """Encapsulates required objects for building and sending the main menu form"""
        Forms.build_main_menu(slack_api=self.st, user=user_id, channel=channel)

    # General support methods
    # ====================================================

    @staticmethod
    def show_gsheets_link() -> str:
        return f'https://docs.google.com/spreadsheets/d/{vik_app.vik_creds.viktor_sheet}/'

    @staticmethod
    def show_onboring_link() -> str:
        return f'https://docs.google.com/document/d/{vik_app.vik_creds.onboarding_key}/edit?usp=sharing'

    def get_channel_stats(self, channel: str) -> str:
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
        # Get list of users based on the ids we've got
        users = self.st.get_users_info(res_df['user'].tolist(), throw_exception=False)
        user_names = []
        for user in users:
            uid = user['id']
            try:
                name = user['profile']['display_name']
            except KeyError:
                name = user['real_name']

            if name == '':
                name = user['real_name']
            user_names.append({'id': uid, 'display_name': name})

        user_names_df = pd.DataFrame(user_names).drop_duplicates()
        res_df = res_df.merge(user_names_df, left_on='user', right_on='id', how='left')\
            .drop(['user', 'id'], axis=1).fillna('Unknown User')
        res_df = res_df[['display_name', 'total_messages', 'avg_msg_len']]
        res_df['total_messages'] = res_df['total_messages'].astype(int)
        res_df['avg_msg_len'] = res_df['avg_msg_len'].round(1)
        res_df = res_df.sort_values('total_messages', ascending=False)
        response = '*Stats for this channel:*\n Total messages examined: {}\n' \
                   '```{}```'.format(len(msgs), self.st.df_to_slack_table(res_df))
        return response

    def refresh_emojis(self) -> List[str]:
        """Refreshes the list of emojis"""
        return self.session.query(TableEmojis.name).filter(TableEmojis.is_denylisted == False).all()

    def get_emojis_like(self, match_pattern: str, message: str, max_res: int = 500) -> str:
        """Gets emojis matching in the system that match a given regex pattern"""

        # Parse out the initial command via regex
        ptrn = re.sub(match_pattern, '', message).strip()

        if ptrn != '':
            # We've got a pattern to use
            pattern = re.compile(ptrn)
            emojis = self.st.get_emojis()
            matches = [k for k, v in emojis.items() if pattern.match(k)]
            len_match = len(matches)
            if len_match > 0:
                # Slack apparently handles message length limitations on its end, so
                #   let's just put all the emojis together into one string
                response = ''.join([':{}:'.format(x) for x in matches[:max_res]])
            else:
                response = 'No results for pattern `{}` :frowning:'.format(ptrn)

            if len_match >= max_res:
                # Append to the emoji_str that it was truncated
                trunc_resp = '`**Truncated Results ({}) -> ({})**`'.format(len_match, max_res)
                response = '{}\n{}'.format(trunc_resp, response)
        else:
            response = "I couldn't find a pattern from your message. Get your shit together <@{user}>"
        return response

    # Basic / Static standalone methods
    # ====================================================
    @staticmethod
    def sarcastic_response() -> str:
        """Sends back a sarcastic response when user is not allowed to use the action requested"""
        sarcastic_reponses = [
            ''.join([':ah-ah-ah:'] * randint(0, 50)),
            'Lol <@{user}>... here ya go bruv :pick:',
            'Nah boo, we good.',
            'Yeah, how about you go on ahead and, you know, do that yourself.'
            ':bye_felicia:'
        ]

        return sarcastic_reponses[randint(0, len(sarcastic_reponses) - 1)]

    @staticmethod
    def giggle() -> str:
        """Laughs, uncontrollably at times"""
        # Count the 'no's
        laugh_cycles = randint(1, 500)
        response = f'ti{"hi" * laugh_cycles}!'
        return response

    @staticmethod
    def overly_polite(message: str) -> str:
        """Responds to 'no, thank you' with an extra 'no' """
        # Count the 'no's
        no_cnt = message.count('no')
        no_cnt += 1
        response = '{}, thank you!'.format(', '.join(['no'] * no_cnt)).capitalize()
        return response

    @staticmethod
    def shurg(message: str) -> str:
        """Shrugs at the front"""
        return f'¯\\_(ツ)_/¯ {message.replace("shurg", "").strip()}'

    @staticmethod
    def shrugg(message: str) -> str:
        """Shrugs at the back"""
        return f'{message.replace("shrug", "").strip()} ¯\\_(ツ)_/¯'

    @staticmethod
    def randcap(message: str) -> str:
        """Randomly capitalize string"""
        message = ' '.join(message.split()[1:])
        weights = (str.lower, str.upper)
        return ''.join(choice(weights)(c) for c in message) + ' :spongebob-mock:'

    @staticmethod
    def word_emoji(message: str, match_pattern: str) -> str:
        """Randomly capitalize string"""
        msg = re.sub(match_pattern, '', message).strip()
        return ''.join(f':alphabet-yellow-{c}:' if c.lower() in string.ascii_lowercase else c for c in msg)

    @staticmethod
    def access_something() -> str:
        """Return random number of ah-ah-ah emojis (Jurassic Park movie reference)"""
        return ''.join([':ah-ah-ah:'] * randint(5, 50))

    @staticmethod
    def get_time() -> str:
        """Gets the server time"""
        return f'The server time is `{dt.today():%F %T}`'

    @staticmethod
    def wfh_epoch() -> List[dict]:
        """Calculates WFH epoch time"""
        wfh_epoch = dt(year=2020, month=3, day=3, hour=19, minute=15)
        now = dt.now()
        diff = (now - wfh_epoch)
        wfh_secs = diff.total_seconds()
        strange_units = {
            'dog years_2': (wfh_secs / (60 * 60 * 24)) / 52,
            'hollow months_2': wfh_secs / (60 * 60 * 24 * 29),
            'fortnights_1': wfh_secs / (60 * 60 * 24 * 7 * 2),
            'kilowarhols_1': wfh_secs / (60 * 15000),
            'weeks_1': wfh_secs / (60 * 60 * 24 * 7),
            'sols_1': wfh_secs / (60 * 60 * 24 + 2375),
            'microcenturies_0': wfh_secs / (52 * 60 + 35.76),
            'Kermits_1': wfh_secs / 60 / 14.4,
            'moments_0': wfh_secs / 90,
            'millidays_2': wfh_secs / 86.4,
            'microfortnights_2': wfh_secs * 1.2096,
        }

        units = []
        for k, v in strange_units.items():
            unit, decimals = k.split('_')
            decimals = int(decimals)
            base_txt = f',.{decimals}f'
            txt = '`{{:<20}} {{:>15{}}}`'.format(base_txt).format(f'{unit.title()}:', v)
            units.append(txt)

        unit_txt = '\n'.join(units)
        return [
            bkb.make_context_section([
                bkb.markdown_section('WFH Epoch')
            ]),
            bkb.make_block_section(
                f'Current WFH epoch time is *`{wfh_secs:.0f}`*.'
                f'\n ({diff})',
            ),
            bkb.make_context_section([
                bkb.markdown_section(f'{unit_txt}')
            ])
        ]

    # Misc. methods
    # ====================================================
    def sh_response(self) -> str:
        """Responds to SHs"""
        responses = [x.text for x in
                     self.session.query(TableResponses).filter(TableResponses.type == 'stakeholder').all()]
        return responses[randint(0, len(responses) - 1)]

    def inspirational(self, channel: str):
        """Sends a random inspirational message"""
        resp = requests.get('https://inspirobot.me/api?generate=true')
        if resp.status_code == 200:
            url = resp.text
            # Download img
            img = requests.get(url)
            if img.status_code == 200:
                with open('/tmp/inspirational.jpg', 'wb') as f:
                    f.write(img.content)
                self.st.upload_file(channel, '/tmp/inspirational.jpg', 'inspirational-shit.jpg')

    def button_game(self):
        """Renders 5 buttons that the user clicks - one button has a value that awards them points"""
        btn_blocks = []
        # Determine where to hide the value
        n_buttons = randint(5, 16)
        items = list(range(1, n_buttons + 1))
        emojis = [self.emoji_list[x] for x in np.random.choice(len(self.emoji_list), len(items), False)]
        rand_val = randint(1, n_buttons)
        # Pick two places where negative values should go
        neg_items = list(np.random.choice([x for x in items if x != rand_val], int(n_buttons/2), False))
        neg_values = []
        win = 0
        for i in items:
            if i == rand_val:
                val = np.random.choice(50, 1)[0]
                win = val
            elif i in neg_items:
                val = np.random.choice(range(-50, 0), 1)[0]
                neg_values.append(val)
            else:
                val = 0
            btn_blocks.append(bkb.make_action_button(f':{emojis[i - 1]}', value=f'buttongame-{val + 500}',
                                                     action_id=f'buttongame-{i}'))

        blocks = [
            bkb.make_context_section([
                bkb.markdown_section('Try your luck and guess which button is hiding the LTITs!!'
                                     f'Only one value has `{win}` LTITs, {len(neg_values)} others have '
                                     f'{",".join([f"`{x}`" for x in neg_values])}. The rest are `0`.')
            ]),
            bkb.make_action_button_group(btn_blocks)
        ]

        return blocks

    def translate_that(self, channel: str, ts: str, message: str, pattern: str) -> Union[str, List[dict]]:
        """Retrieves previous message and tries to translate it into whatever the target language is"""
        target_lang = 'et'
        if pattern is not None:
            msg = re.sub(pattern, '', message).strip()
            if msg == '':
                return 'No target language code specified!'
            target_lang = msg.split()[0]
            if len(target_lang) != 2:
                # Probably not a proper language code?
                return f'Unrecognized language code {target_lang}'

        prev_msg = self.st.get_prev_msg_in_channel(channel, ts,
                                                   callable_list=[self.translate_anything, 'text', None,
                                                                  target_lang, False])
        if isinstance(prev_msg, str):
            # The callable above only gets called when we're working with a block
            return self.translate_anything(prev_msg, target=target_lang)
        else:
            return prev_msg

    def translate_anything(self, message: str, match_pattern: str = None, target: str = None,
                           block_return: bool = True) -> Union[str, List[dict]]:
        """Attempts to translate any phrase into the target language defined at the beginning of the command"""
        if match_pattern is not None:
            # Request came directly
            msg = re.sub(match_pattern, '', message).strip()
            if msg == '':
                return 'Missing language code and content.'
            msg_split = msg.split()
            target_lang = msg_split[0]
            text = ' '.join(msg_split[1:])
        else:
            # Request came indirectly
            if target is not None:
                target_lang = target
                text = message
            else:
                msg_split = message.split()
                target_lang = msg_split[0]
                text = ' '.join(msg_split[1:])

        if len(target_lang) != 2:
            # Probably not a proper language code?
            return f'Unrecognized language code {target_lang}'

        # Get a dictionary showing the source/target languages,
        #   as well as the confidence and the translation itself
        lang_dict = self.ling.translate_anything(text=text, target_lang=target_lang)

        if block_return:
            return [
                bkb.make_context_section([
                    bkb.markdown_section('*`{src_name} -> {tgt_name}`*\t '
                                         'src lang confidence:\t{conf:.1%}'.format(**lang_dict))
                ]),
                bkb.make_block_divider(),
                bkb.make_block_section(lang_dict['translation'])
            ]
        else:
            return lang_dict['translation']

    def uwu_that(self, channel: str, ts: str) -> Union[str, List[dict]]:
        """Retrieves previous message and converts to UwU"""

        prev_msg = self.st.get_prev_msg_in_channel(channel, ts, callable_list=[self.uwu, 'text'])
        if isinstance(prev_msg, str):
            # The callable above only gets called when we're working with a block
            return self.uwu(prev_msg)
        else:
            return prev_msg

    def uwu(self, msg: str) -> str:
        """uwu-fy a message"""
        default_lvl = 2

        if '-l' in msg.split():
            level = msg.split()[msg.split().index('-l') + 1]
            level = int(level) if level.isnumeric() else default_lvl
            text = ' '.join(msg.split()[msg.split().index('-l') + 2:])
        else:
            level = default_lvl
            text = msg.replace('uwu', '').strip()

        chars = [x.graphic for x in self.session.query(TableUwu).all()]

        if level >= 1:
            # Level 1: Letter replacement
            text = text.translate(str.maketrans('rRlL', 'wWwW'))

        if level >= 2:
            # Level 2: Placement of 'uwu' when certain patterns occur
            pattern_allowlist = {
                'uwu': {
                    'start': 'u',
                    'anywhere': ['nu', 'ou', 'du', 'un', 'bu'],
                },
                'owo': {
                    'start': 'o',
                    'anywhere': ['ow', 'bo', 'do', 'on'],
                }
            }
            # Rebuild the phrase letter by letter
            phrase = []
            for word in text.split(' '):
                roll = randint(1, 10)
                if roll < 3:
                    word = f'{word[0]}-{word}'
                for pattern, pattern_dict in pattern_allowlist.items():
                    if word.startswith(pattern_dict['start']):
                        word = word.replace(pattern_dict['start'], pattern)
                    else:
                        for fragment in pattern_dict['anywhere']:
                            if fragment in word:
                                word = word.replace(pattern_dict['start'], pattern)
                phrase.append(word)
            text = ' '.join(phrase)

            # Last step, insert random characters
            prefix_emoji = chars[np.random.choice(len(chars), 1)[0]].graphic
            suffix_emoji = chars[np.random.choice(len(chars), 1)[0]].graphic
            text = f'{prefix_emoji} {text} {suffix_emoji}'

        return text.replace('`', ' ')

    def quote_me(self, message: str, match_pattern: str) -> Optional[str]:
        """Converts message into letter emojis"""
        msg = re.sub(match_pattern, '', message).strip()
        return self.st.build_phrase(msg)

    def add_emoji_form_p1(self, user: str, channel: str):
        """Builds form to intake emoji and upload"""
        form1 = Forms.build_new_emoji_form_p1()
        resp = self.st.private_channel_message(user_id=user, channel=channel, message='New emoji form, p1',
                                               blocks=form1)

    def add_emoji_form_p2(self, user: str, channel: str, url: str):
        """Part 2 of emoji intake"""
        form2 = Forms.build_new_emoji_form_p2(url)
        resp = self.st.private_channel_message(user_id=user, channel=channel, message='New emoji form, p1',
                                               blocks=form2)

    def add_emoji(self, user: str, channel: str, url: str, new_name: str):
        """Attempts to upload new emoji"""
        success = self.st.session.upload_emoji_from_url(url, new_name)
        if success:
            msg = f'Success! Here\'s how your emoji looks: :{new_name}:'
        else:
            msg = 'Something went wrong. Unable to upload the emoji at this time. ' \
                  'Make sure the emoji name you chose is not already in use. ' \
                  f'(Hint: if it is, there will be an emoji here: :{new_name}:'
        self.st.private_channel_message(user_id=user, channel=channel, message=msg)

    # Phrase building methods
    # ------------------------------------------------
    def guess_acronym(self, message: str) -> str:
        return self.pb.guess_acronym(message, self.session)

    def insult(self, message: str) -> str:
        return self.pb.insult(message, session=self.session)

    def phrase_generator(self, message: str) -> str:
        return self.pb.phrase_generator(message, session=self.session)

    def compliment(self, raw_message: str, user: str) -> str:
        return self.pb.compliment(raw_message, user, session=self.session)

    def facts(self):
        return self.pb.facts(session=self.session)

    # OKR Methods
    # ------------------------------------------------
    def onboarding_docs(self) -> List[dict]:
        """Returns links to everything needed to bring a new OKR employee up to speed"""
        docs = [
            bkb.make_block_section([
                "Welcome to OKR! We're glad to have you on board!\nCheck out these links below "
                "to get familiar with OKR and the industry we support!"
            ]),
            bkb.make_block_section([
                f"\t<{self.show_onboring_link()}|Onboarding Doc>\n\t<{self.show_gsheets_link()}|Viktor's GSheet>\n"
            ]),
            bkb.make_block_section([
                "For any questions, reach out to the CEO or our Head of Recruiting. "
                "Don't know who they are? Well, figure it out!"
            ])
        ]
        return docs

    def show_all_perks(self) -> List[Dict]:
        """Displays all the perks"""
        perks = self.session.query(TablePerks).all()
        final_perks = self._build_perks_list(perks)
        return [
            bkb.make_header('OKR Perks!'),
            bkb.make_context_section([
                bkb.markdown_section('you\'ll never see anything better, trust us!')
            ]),
            bkb.make_block_section([p for p in final_perks])
        ]

    @staticmethod
    def _build_perks_list(perks: List[TablePerks]) -> List[str]:
        """Builds out a formatted list of perks based on a filtered query result from the table"""
        perk_dict = {}
        for perk in perks:
            # Organize perks by level
            level = perk.level
            if level in perk_dict.keys():
                perk_dict[level].append(perk.desc)
            else:
                perk_dict[level] = [perk.desc]
        # Sort by keys, just in case they're not in order
        perk_dict = dict(sorted(perk_dict.items()))
        final_perks = []
        for level, perk_list in perk_dict.items():
            formatted_perk_list = '\n\t\t - '.join(perk_list)
            final_perks.append(f'`lvl {level}`: \n\t\t - {formatted_perk_list}\n')
        return final_perks

    def show_my_perks(self, user: str) -> Union[List[Dict], str]:
        """Lists the perks granted at the user's current level"""
        # Get the user's level
        user_data = self.session.query(TableUsers).filter(TableUsers.slack_id == user).one_or_none()
        if user_data is None:
            return 'User not found in OKR roles sheet :frowning:'

        level = user_data.level
        ltits = user_data.ltits

        # Get perks
        perks = self.session.query(TablePerks).filter(TablePerks.level <= level).all()
        final_perks = self._build_perks_list(perks)
        return [
            bkb.make_header(f'Perks for <@{user}>!'),
            bkb.make_context_section([
                bkb.markdown_section('you\'ll _really_ never see anything better, trust us!')
            ]),
            bkb.make_block_section('Here are the _amazing_ perks you have unlocked!!'),
            bkb.make_block_section([p for p in final_perks]),
            bkb.make_block_section(f'...and don\'t forget you have *`{ltits}`* LTITs! That\'s something, too!')
        ]

    def update_user_level(self, channel: str, user: str, message: str, match_pattern: str) -> Optional[str]:
        """Increment the user's level"""
        content = re.sub(match_pattern, '', message).strip()

        if user not in self.approved_users:
            return 'LOL sorry, levelups are CEO-approved only'

        if '-u' in content:
            # Updating role of other user
            # Extract user
            user = content.split()[1].replace('<@', '').replace('>', '').upper()
            if user == 'UPLAE3N67':
                # Some people should stay permanently at lvl 1
                return 'Hmm... that\'s weird. It says you can\'t be leveled up??'

            user_obj = self.session.query(TableUsers).filter(TableUsers.slack_id == user).one_or_none()
            if user is None:
                return f'user <@{user}> not found in HR records... :nervous_peach:'
            user_obj.level += 1
            self.session.commit()
            self.st.send_message(channel, f'Level for *`{user_obj.name}`* updated to *`{user_obj.level}`*.')
        else:
            return 'No user tagged for update.'

    def update_user_ltips(self, channel: str, user: str, message: str, match_pattern: str = None) -> Optional[str]:
        """Increment the user's level"""
        if match_pattern is not None:
            content = re.sub(match_pattern, '', message).strip()
        else:
            content = message

        if user not in self.approved_users:
            return 'LOL sorry, LTIT distributions are CEO-approved only'

        if '-u' in content:
            # Updating role of other user
            # Extract user
            user = content.split()[1].replace('<@', '').replace('>', '').upper()
            points = content.split()[-1]
            if points.replace('-', '').replace('+', '').isnumeric():
                ltits = int(points.replace('-', '').replace('+', ''))
                ltits = ltits * -1 if '-' in points else ltits
                if not -1000 < ltits < 1000:
                    # Limit the number of ltits that can be distributed at any given time
                    ltits = 1000 if ltits > 1000 else -1000
                user_obj = self.session.query(TableUsers).filter(TableUsers.slack_id == user).one_or_none()
                if user is None:
                    return f'user <@{user}> not found in HR records... :nervous_peach:'
                user_obj.ltits += ltits
                self.session.commit()
                self.st.send_message(
                    channel, f'LTITs for  *`{user_obj.name}`* updated by *`{ltits}`* to *`{user_obj.ltits}`*.')
            else:
                return 'Please put points at the end. (+n, -n, n)'
        else:
            return 'No user tagged for update.'

    def update_roles(self, user: str, channel: str, msg: str, match_pattern: str) -> Optional:
        """Updates a user with their role"""
        content = re.sub(match_pattern, '', msg).strip()

        if '-u' in content:
            # Updating role of other user
            # Extract user
            user = content.split()[1].replace('<@', '').replace('>', '').upper()
            content = ' '.join(content.split()[2:])
        # TODO this
        return 'TBD!'

    def show_roles(self, user: str = None) -> Union[List[Dict], str]:
        """Prints users roles to channel"""
        roles_output = []
        if user is None:
            # Printing roles for everyone
            roles_output += [
                bkb.make_header('OKR Roles'),
                bkb.make_context_section([
                    bkb.markdown_section('_(as of last reorg)_')
                ])
            ]
            # Iterate through roles, print them out
            for u in self.session.query(TableUsers).all():
                role = u.role if u.role is not None else 'You take the specifications from the customers, ' \
                                                         'and you bring them down to the software engineers'
                role_desc = u.role_desc if u.role_desc is not None else 'What would you say... you do here?'
                roles_output.append(bkb.make_block_section([
                    f'*`{u.name}`*: Level *`{u.level}`* (*`{u.ltits}*` LTITs)\n\t\t*{role}*\n\t\t\t{role_desc}'
                ]))
        else:
            # Printing role for an individual user
            user_obj = self.session.query(TableUsers).filter(TableUsers.slack_id == user).one_or_none()
            if user is None:
                return f'user <@{user}> not found in HR records... :nervous_peach:'
            role = user_obj.role if user_obj.role is not None else 'You take the specifications from the ' \
                                                                   'customers, and you bring them down to the ' \
                                                                   'software engineers.'
            role_desc = user_obj.role_desc if user_obj.role_desc is not None else 'What would you say... you do here?'
            roles_output.append(bkb.make_block_section([
                f'*`{user_obj.name}`*: Level *`{user_obj.level}`* (*`{user_obj.ltits}*` LTITs)'
                f'\n\t\t*{role}*\n\t\t\t{role_desc}'
            ]))

        return roles_output

    def build_role_txt(self, channel: str, user: str = None):
        """Constructs a text blob consisting of roles without exceeding the character limits of Slack"""
        roles_output = self.show_roles(user)
        self.st.send_message(channel, message='Roles output', blocks=roles_output)
