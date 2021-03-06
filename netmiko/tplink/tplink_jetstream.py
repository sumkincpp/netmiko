import re
import time

from cryptography import utils as crypto_utils
from cryptography.hazmat.primitives.asymmetric import dsa

from netmiko import log
from netmiko.cisco_base_connection import CiscoSSHConnection


class TPLinkJetStreamBase(CiscoSSHConnection):
    def __init__(self, **kwargs):
        # TP-Link doesn't have a way to set terminal width which breaks cmd_verify
        if kwargs.get("global_cmd_verify") is None:
            kwargs["global_cmd_verify"] = False
        # TP-Link uses "\r\n" as default_enter for SSH and Telnet
        if kwargs.get("default_enter") is None:
            kwargs["default_enter"] = "\r\n"
        return super().__init__(**kwargs)

    def session_preparation(self):
        """
        Prepare the session after the connection has been established.
        """
        delay_factor = self.select_delay_factor(delay_factor=0)
        time.sleep(0.3 * delay_factor)
        self.clear_buffer()
        self._test_channel_read(pattern=r"[>#]")
        self.set_base_prompt()
        self.enable()
        self.disable_paging()
        # Clear the read buffer
        time.sleep(0.3 * self.global_delay_factor)
        self.clear_buffer()

    def enable(self, cmd="enable", pattern="ssword", re_flags=re.IGNORECASE):
        """
        Enter enable mode.

        If the user does not have the Admin role it will need to execute
        enable-admin to really enable all functions.
        """
        fallback_cmd = "enable-admin"
        try:
            return super().enable(cmd=cmd, pattern=pattern, re_flags=re_flags)
        except ValueError:
            return super().enable(cmd=fallback_cmd, pattern=pattern, re_flags=re_flags)

    def config_mode(self, config_command="configure"):
        """Enter configuration mode."""
        return super().config_mode(config_command=config_command)

    def exit_config_mode(self, exit_config="exit", pattern=r"#"):
        """
        Exit config mode.

        Like the Mellanox equipment, the TP-Link Jetstream does not
        support a single command to completely exit the configuration mode.

        Consequently, need to keep checking and sending "exit".
        """
        output = ""
        check_count = 12
        while check_count >= 0:
            if self.check_config_mode():
                self.write_channel(self.normalize_cmd(exit_config))
                output += self.read_until_pattern(pattern=pattern)
            else:
                break
            check_count -= 1

        if self.check_config_mode():
            raise ValueError("Failed to exit configuration mode")
            log.debug(f"exit_config_mode: {output}")

        return output

    def check_config_mode(self, check_string="(config", pattern=r"#"):
        """Check whether device is in configuration mode. Return a boolean."""
        return super().check_config_mode(check_string=check_string, pattern=pattern)

    def set_base_prompt(
        self, pri_prompt_terminator=">", alt_prompt_terminator="#", delay_factor=1
    ):
        """
        Sets self.base_prompt

        Used as delimiter for stripping of trailing prompt in output.

        Should be set to something that is general and applies in multiple
        contexts. For TP-Link this will be the router prompt with > or #
        stripped off.

        This will be set on logging in, but not when entering system-view
        """
        prompt = super().set_base_prompt(
            pri_prompt_terminator=pri_prompt_terminator,
            alt_prompt_terminator=alt_prompt_terminator,
            delay_factor=delay_factor,
        )

        prompt = prompt.strip()
        self.base_prompt = prompt
        return self.base_prompt


class TPLinkJetStreamSSH(TPLinkJetStreamBase):
    def _override_check_dsa_parameters(parameters):
        """
        Override check_dsa_parameters from cryptography's dsa.py

        Without this the error below occurs:

        ValueError: p must be exactly 1024, 2048, or 3072 bits long

        Allows for shorter or longer parameters.p to be returned
        from the server's host key. This is a HORRIBLE hack and a
        security risk, please remove if possible!

        By now, with firmware:

        2.0.5 Build 20200109 Rel.36203(s)

        It's still not possible to remove this hack.
        """
        if crypto_utils.bit_length(parameters.q) not in [160, 256]:
            raise ValueError("q must be exactly 160 or 256 bits long")

        if not (1 < parameters.g < parameters.p):
            raise ValueError("g, p don't satisfy 1 < g < p.")

    dsa._check_dsa_parameters = _override_check_dsa_parameters


class TPLinkJetStreamTelnet(TPLinkJetStreamBase):
    def telnet_login(
        self,
        pri_prompt_terminator="#",
        alt_prompt_terminator=">",
        username_pattern=r"User:",
        pwd_pattern=r"Password:",
        delay_factor=1,
        max_loops=60,
    ):
        """Telnet login: can be username/password or just password."""
        super().telnet_login(
            pri_prompt_terminator=pri_prompt_terminator,
            alt_prompt_terminator=alt_prompt_terminator,
            username_pattern=username_pattern,
            pwd_pattern=pwd_pattern,
            delay_factor=delay_factor,
            max_loops=max_loops,
        )
