"""
DHCPKit internals
"""
import sys

from dhcpkit import typing

__version__ = '1.0.2'

# Make sure we have a usable typing module
sys.modules['typing'] = typing
