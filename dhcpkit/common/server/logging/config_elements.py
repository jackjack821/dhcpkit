"""
The basic configuration objects for logging
"""
import logging
import logging.handlers

import os
from ZConfig.datatypes import SocketAddress
from ZConfig.matcher import SectionValue

from dhcpkit.common.server.config_elements import ConfigElementFactory, ConfigSection
from dhcpkit.common.server.logging.verbosity import set_verbosity_logger


class Logging(ConfigSection):
    """
    Class managing the configured logging handlers.
    """

    def validate_config_section(self):
        """
        Check for duplicate handlers
        """
        # Check that we don't have multiple console loggers
        have_console = False
        for handler_factory in self._section.handlers:
            if isinstance(handler_factory, ConsoleHandlerFactory):
                if have_console:
                    raise ValueError("You cannot log to the console multiple times")
                have_console = True

    def configure(self, logger: logging.Logger, verbosity: int = 0):
        """
        Add all configured handlers to the supplied logger. If verbosity > 0 then make sure we have a console logger
        and force the level of the console logger based on the verbosity.

        :param logger: The logger to add the handlers to
        :param verbosity: The verbosity level given as command line argument
        """
        # Remove any previously configured loggers, in case we are re-configuring
        # We are deleting, so copy the list first
        for handler in list(logger.handlers):
            logger.removeHandler(handler)

        # Add the handlers, keeping track of console loggers and saving the one with the "best" level.
        console = None
        for handler_factory in self._section.handlers:
            handler = handler_factory()
            logger.addHandler(handler)

            if isinstance(handler_factory, ConsoleHandlerFactory):
                console = handler

        # Set according to verbosity
        set_verbosity_logger(logger, verbosity, console)


class ConsoleHandlerFactory(ConfigElementFactory):
    """
    Factory for a logging handler that logs to the console, optionally in colour.
    """

    def __init__(self, section: SectionValue):
        self.colorlog = None
        super().__init__(section)

    def validate_config_section(self):
        """
        Validate the colorlog setting
        """
        # Try loading colorlog
        try:
            if self._section.color is False:
                # Explicitly disabled
                colorlog = None
            else:
                # noinspection PyPackageRequirements
                import colorlog
        except ImportError:
            if self._section.color is True:
                # Explicitly enabled, and failed
                raise ValueError("Colored logging turned on but the 'colorlog' package is not installed")

            colorlog = None

        self.colorlog = colorlog

    def create(self) -> logging.StreamHandler:
        """
        Create a console handler

        :return: The logging handler
        """
        handler = logging.StreamHandler()

        if self.colorlog:
            formatter = self.colorlog.ColoredFormatter('{yellow}{asctime}{reset} '
                                                       '[{log_color}{levelname}{reset}] '
                                                       '{message}',
                                                       datefmt=logging.Formatter.default_time_format,
                                                       style='{')
        else:
            formatter = logging.Formatter('{asctime} [{levelname}] {message}',
                                          datefmt=logging.Formatter.default_time_format,
                                          style='{')

        handler.setFormatter(formatter)
        handler.setLevel(self._section.level)

        return handler


class FileHandlerFactory(ConfigElementFactory):
    """
    Factory for a logging handler that logs to a file, optionally rotating it.
    """

    def __init__(self, section: SectionValue):
        self.path = None
        super().__init__(section)

    def validate_config_section(self):
        """
        Validate if the combination of settings is valid
        """
        # noinspection PyProtectedMember
        existing_relative_dirpath = self._section._matcher.type.registry.get('existing-relative-dirpath')
        self.path = existing_relative_dirpath(self._section.getSectionName())

        # Size-based rotation and specifying a size go together
        if self._section.size and self._section.rotate != 'SIZE':
            raise ValueError("You can only specify a size when rotating based on size")
        elif not self._section.size and self._section.rotate == 'SIZE':
            raise ValueError("When rotating based on size you must specify a size")

        # Rotation and keeping old logs go together
        if self._section.keep and not self._section.rotate:
            raise ValueError("You can only specify how many log files to keep when rotation is enabled")
        elif not self._section.keep and self._section.rotate:
            raise ValueError("You must specify how many log files to keep when rotation is enabled")

    def create(self) -> logging.StreamHandler:
        """
        Create a console handler

        :return: The logging handler
        """
        if self._section.rotate == 'SIZE':
            # Rotate based on file size
            handler = logging.handlers.RotatingFileHandler(filename=self.path,
                                                           maxBytes=self._section.size,
                                                           backupCount=self._section.keep)
            handler.setLevel(self._section.level)
            return handler
        elif self._section.rotate is not None:
            # Rotate on time
            handler = logging.handlers.TimedRotatingFileHandler(filename=self.path,
                                                                when=self._section.rotate,
                                                                backupCount=self._section.keep)
            handler.setLevel(self._section.level)
            return handler
        else:
            # No rotation specified, used a WatchedFileHandler so that external rotation works
            return logging.handlers.WatchedFileHandler(filename=self._section.path)


class SysLogHandlerFactory(ConfigElementFactory):
    """
    Factory for a logging handler that logs to syslog.
    """
    default_destinations = (
        '/dev/log',
        '/var/run/syslog',
        'localhost:514',
    )

    def __init__(self, section):
        super().__init__(section)

        # The name is the destination
        self.destination = section.getSectionName()

        if self.destination:
            # Apply the correct datatype
            self.destination = SocketAddress(self.destination)
        else:
            # Fallback in case no destination is specified
            for destination in self.default_destinations:
                if destination.startswith('/'):
                    if os.path.exists(destination):
                        # Destination is a path, check if it exists
                        self.destination = SocketAddress(destination)
                        break
                else:
                    # Not a path, just assume it's ok
                    self.destination = SocketAddress(destination)
                    break

    def create(self) -> logging.handlers.SysLogHandler:
        """
        Create a syslog handler

        :return: The logging handler
        """
        handler = logging.handlers.SysLogHandler(address=self.destination.address,
                                                 facility=self._section.facility,
                                                 socktype=self._section.protocol)
        handler.setLevel(self._section.level)
        return handler