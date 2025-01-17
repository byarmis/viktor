"""Configuration setup"""
from viktor import (
    __update_date__,
    __version__,
)


class Common(object):
    """Configuration items common across all config types"""

    BOT_FIRST_NAME = 'Viktor Boborkadork Ivanovich'
    BOT_NICKNAME = 'viktor'
    ADMINS = ['UM35HE6R5']

    VERSION = __version__
    UPDATE_DATE = __update_date__

    TEST_CHANNEL = 'CM376Q90F'
    EMOJI_CHANNEL = 'CLWCPQ2TV'
    GENERAL_CHANNEL = 'CMEND3W3H'


class Development(Common):
    """Configuration for development environment"""
    ENV = 'DEV'
    BOT_LAST_NAME = 'Debugnatov'
    MAIN_CHANNEL = 'CM376Q90F'  # #test
    TRIGGERS = ['biktor', 'b!']
    DEBUG = True


class Production(Common):
    """Configuration for development environment"""
    ENV = 'PROD'
    BOT_LAST_NAME = 'Produdnikov'
    MAIN_CHANNEL = 'CMEND3W3H'  # #general
    TRIGGERS = ['viktor', 'v!']
    DEBUG = False
