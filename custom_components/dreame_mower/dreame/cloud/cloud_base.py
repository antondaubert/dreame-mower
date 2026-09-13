"""Base authentication class for Dreame cloud services."""

import base64
import logging
import hashlib
import json
import queue
import random
import requests
import time
import zlib
from threading import Thread
from time import sleep
from typing import Any, Dict, Final, List, Optional

_LOGGER = logging.getLogger(__name__)

DREAME_STRINGS: Final = "H4sICAAAAAAEAGNsb3VkX3N0cmluZ3MuanNvbgBdUltv2jAU/iuoUtEmjZCEljBVPDAQgu0hK5eudJrQwXaIV18y24yyX79jm45tebDPd67f+ZyvVwnXLqGGgWSJY6S+eneV9fJ+gfdidBKb8XUll5+a4nr1A12TkLhdSjCu1pJ1s+Q2uX3fesM/11qxuxYvl62sn6R3rSUBwbq9JE3f+p5kkO56xaDY5Xm/XxT9HaHkZpBVvYIOKrjJd5Cl0EuhGmTQp1Unw6IPYDlpPc0+is2XTDzm0yOZbV7K5+n9o1zk97NmtM6mTw+qLsvJfogFafjQsA7cwaIhwTpm1pyiveOKTrQErhA0RjfMuBOaqMCcepcAV2kjh/Ny2bYE40MQor03oNzWnRBikmGVYbbeOv3MVPsf5MMNWHvUhrYPlhkFMtS0X70BhE5AiD4oh7gbxe/AwdVdHc7QDUOYxKyNzS+j/2D20nB0bHkM7rn2hmPK8w0bn1t7Lh3cMu7qkZcioqjUJULBga9kPzlhaAhu3UPu46rSMVCuxvMItCPeCnsbkPacH/DeV0tNmQjsCK5vL5RwWodo6Z+KKTrWUsIro4oLX+ovL+D5rXytVw6vGkdo419uz9wkEJ1E1vY/PInDRigqorWXYbRnyl1CC0EQ+ARt+C9wUcNV0LAT/oqxVo4hWMXh0DSCk5DY/W5DdrPFY3umo49KaKBrI6KjtDajf3u//QbhJuZXdAMAAA=="
MOVA_STRINGS: Final = "H4sIAAAAAAAAA11Sa2/aMBT9K6hS0SYtIQktYar6gYEQ3TRlLdC1nabo4jjEqx+ZbUrZr5+vY7p2+eDcc+772D9OYqZsLNQTRJaSJiZKnHzonaTDbJSjcTM58PvpaS2WX9r8dPUbua8uulwK0LZRgg7S+Dw+/9h7x741StKLHiuWvXQUJxe9JQFOB8M4Sd77omScbIb5ON9k2WiU56MNqcjZOK2HeTWu4SzbQJrAMIF6nMKoqqMUsz6BYaT3sPjM77+n/C6b78ni/rl4nF/fiZvsetFO1un84VY2RTHbXmJGgl+GlrFgdwYtAcZSvWYVgg2T1UwJYBJRq1VLtT2g7cS48iEtB1srLS6vimXfEBdxCZz3txqkLe3BQYzStNbUNKVVj1T23yDvb8GYvdJVf2eoliC6rP6R7pCvBoSonbRIDCpNXWgEO9sMlD99RfS5MGpM+YLftESCPrfMMSUL7i1T3rJU4uTd/qEBDhW5jcPiCFGZAP9pF3wVWPDZ9IkRihZnxt56oZmsVfAVq+lVQMqSo9mCBmGOSR2z9UWEqijvhiVOE/NqQNc4Cg/SUFlNlRDwMl/NuM/HP0p7vEpfADXFf+OaKe2vdkvtzE8+C3uY/4lZ13XiFEe4RnkmW9rdSnDecIIIY5Rmf8AGfVde36h7PFMlnd42WoUpoG05Iz528Mt0CW2JZ3mcTO0lV1CtNQ9MYUxavaZ//gW/B6/rrAMAAA=="


def _decode_api_strings(encoded: str) -> List[str]:
    return json.loads(zlib.decompress(base64.b64decode(encoded), zlib.MAX_WBITS | 32))


REDACTED: Final = "***"
# Form fields and headers that carry account credentials or session tokens.
_SENSITIVE_FIELDS: Final = frozenset(
    {"username", "password", "refresh_token", "access_token"}
)
_SENSITIVE_HEADERS: Final = frozenset(
    {"authorization", "dreame-auth", "dreame-rlc"}
)


def redact_body(body: Any) -> Any:
    """Mask credential values in a form-encoded request body for logging."""
    if not isinstance(body, str):
        return body

    redacted = []
    for pair in body.split("&"):
        key, separator, _ = pair.partition("=")
        if separator and key.lower() in _SENSITIVE_FIELDS:
            redacted.append(f"{key}={REDACTED}")
        else:
            redacted.append(pair)
    return "&".join(redacted)


def redact_headers(headers: Dict[str, Any]) -> Dict[str, Any]:
    """Mask credential values in request headers for logging."""
    return {
        name: REDACTED if name.lower() in _SENSITIVE_HEADERS else value
        for name, value in headers.items()
    }


class DreameMowerCloudBase:
    """Base class for Dreame cloud operations, authentication and API access."""
    
    def __init__(
        self,
        username: str,
        password: str,
        country: str,
        account_type: str,
    ) -> None:
        """Initialize cloud authentication.
        
        Args:
            username: Cloud account username
            password: Cloud account password  
            country: Country code (e.g., 'us', 'eu', 'cn')
            account_type: Account type ('dreame' or 'mova')
        """
        # Decode API strings based on account type
        if account_type == "dreame":
            self._api_strings = _decode_api_strings(DREAME_STRINGS)
        elif account_type == "mova":
            self._api_strings = _decode_api_strings(MOVA_STRINGS)
        else:
            raise ValueError(f"Unsupported account_type: {account_type}. Must be 'dreame' or 'mova'")
            
        self._username = username
        self._password = password
        self._country = country
        self._location: str = country
        self._session = requests.session()
        self._ti: Optional[str] = None
        self._fail_count = 0
        self.__http_api_connected = False
        self.__logged_in = False
        self._secondary_key: Optional[str] = None
        self._key_expire: Optional[float] = None
        self._key: Optional[str] = None
        self._uuid: Optional[str] = None
        
        # Async API infrastructure
        self._queue: queue.Queue = queue.Queue()
        self._thread: Optional[Thread] = None
        self._id = random.randint(1, 100)

    def get_api_url(self) -> str:
        """Get the base API URL for the configured country."""
        return f"https://{self._country}{self._api_strings[0]}:{self._api_strings[1]}"

    @property
    def connected(self) -> bool:
        """Check if connected to cloud services (logged in and HTTP API accessible)."""
        return self.__logged_in and self.__http_api_connected

    def connect(self) -> bool:
        """Connect and authenticate with Dreame cloud services.
        
        Returns:
            True if connection successful, False otherwise
        """
        self._session.close()
        self._session = requests.session()
        self.__logged_in = False

        try:
            if self._secondary_key:
                data = f"{self._api_strings[12]}{self._api_strings[13]}{self._secondary_key}"
            else:
                data = f"{self._api_strings[12]}{self._api_strings[14]}{self._username}{self._api_strings[15]}{hashlib.md5(((self._password or '') + self._api_strings[2]).encode('utf-8')).hexdigest()}{self._api_strings[16]}"

            headers = {
                "Accept": "*/*",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept-Language": "en-US;q=0.8",
                "Accept-Encoding": "gzip, deflate",
                self._api_strings[47]: self._api_strings[3],
                self._api_strings[49]: self._api_strings[5],
                self._api_strings[50]: self._ti if self._ti else self._api_strings[6],
            }

            if self._country == "cn":
                headers[self._api_strings[48]] = self._api_strings[4]

            response = self._session.post(
                self.get_api_url() + self._api_strings[17],
                headers=headers,
                data=data,
                timeout=10,
            )
            if response.status_code == 200:
                data = json.loads(response.text)
                if self._api_strings[18] in data:
                    self._key = data.get(self._api_strings[18])
                    self._secondary_key = data.get(self._api_strings[19])
                    self._key_expire = time.time(
                    ) + data.get(self._api_strings[20]) - 120
                    self.__logged_in = True
                    self._uuid = data.get("uid")
                    self._location = data.get(
                        self._api_strings[21], self._location)
                    self._ti = data.get(self._api_strings[22], self._ti)
            else:
                try:
                    data = json.loads(response.text)
                    if "error_description" in data and "refresh token" in data["error_description"]:
                        self._secondary_key = None
                        return self.connect()
                except:
                    pass
                _LOGGER.error("Login failed: %s => %s -- %s -- %s", response.text,
                              self.get_api_url() + self._api_strings[17],
                              redact_headers(headers), redact_body(data))
        except requests.exceptions.Timeout:
            response = None
            _LOGGER.warning("Login Failed: Read timed out. (read timeout=10)")
        except Exception as ex:
            response = None
            _LOGGER.error("Login failed: %s", str(ex))

        if self.__logged_in:
            self._fail_count = 0
            self.__http_api_connected = True
        return self.__logged_in

    def get_devices(self) -> Any:
        """Get list of devices associated with the account.
        
        Returns:
            Device list data or None if failed
        """
        if not self.connected:
            raise ConnectionError("get_devices: Not connected. Call connect() first.")
                
        response = self._api_call(
            f"{self._api_strings[23]}/{self._api_strings[24]}/{self._api_strings[27]}/{self._api_strings[28]}")
        if response:
            if "data" in response and response["code"] == 0:
                return response["data"]
        return None

    def _api_call(self, url, params=None, retry_count=2, raise_on_error=False):
        """Make an authenticated API call.
        
        Args:
            url: API endpoint URL
            params: Request parameters
            retry_count: Number of retry attempts
            raise_on_error: If True, raise exceptions on HTTP errors instead of returning None
            
        Returns:
            API response data
        """
        full_url = f"{self.get_api_url()}/{url}"
        data_payload = json.dumps(params, separators=(",", ":")) if params is not None else None
        
        return self.request(full_url, data_payload, retry_count, raise_on_error)

    def _api_task(self):
        """Background task worker for async API calls."""
        while True:
            item = self._queue.get()
            if len(item) == 0:
                self._queue.task_done()
                return
            item[0](self._api_call(item[1], item[2], item[3]))
            sleep(0.1)
            self._queue.task_done()

    def _api_call_async(self, callback, url, params=None, retry_count=2):
        """Make an asynchronous authenticated API call.
        
        Args:
            callback: Function to call with the API response
            url: API endpoint URL
            params: Request parameters
            retry_count: Number of retry attempts
        """
        if self._thread is None:
            self._thread = Thread(target=self._api_task, daemon=True)
            self._thread.start()

        self._queue.put((callback, url, params, retry_count))

    def request(self, url: str, data, retry_count=2, raise_on_error=False) -> Any:
        """Execute HTTP request with authentication.
        
        Args:
            url: Full request URL
            data: Request body data
            retry_count: Number of retry attempts
            
        Returns:
            Parsed JSON response
        """
        retries = 0
        last_exception = None
        if not retry_count or retry_count < 0:
            retry_count = 0
        while retries < retry_count + 1:
            timeout = 20
            try:
                if self._key_expire and time.time() > self._key_expire:
                    self.connect()

                headers = {
                    "Accept": "*/*",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept-Language": "en-US;q=0.8",
                    "Accept-Encoding": "gzip, deflate",
                    self._api_strings[47]: self._api_strings[3],
                    self._api_strings[49]: self._api_strings[5],
                    self._api_strings[50]: self._ti if self._ti else self._api_strings[6],
                    self._api_strings[51]: self._api_strings[52],
                    self._api_strings[46]: self._key,
                }
                if self._country == "cn":
                    headers[self._api_strings[48]] = self._api_strings[4]

                response = self._session.post(
                    url,
                    headers=headers,
                    data=data,
                    timeout=timeout,
                )
                break
            except Exception as ex:
                last_exception = ex
                retries = retries + 1
                response = None
                if self.__http_api_connected:
                    if isinstance(ex, requests.exceptions.Timeout):
                        _LOGGER.warning(
                            "DreameMowerCloudAuth.request: Read timed out. (read timeout=%s) for URL %s: %s",
                            timeout,
                            url,
                            redact_body(data),
                        )
                    else:
                        _LOGGER.warning(
                            "Error while executing request to %s: %s (type: %s)", url, str(ex), type(ex).__name__)
        if response is not None:
            if response.status_code == 200:
                self._fail_count = 0
                self.__http_api_connected = True
                return json.loads(response.text)
            elif response.status_code == 401 and self._secondary_key:
                _LOGGER.warning("Execute api call failed: Token Expired")
                self.connect()
            else:
                _LOGGER.warning(
                    "Execute api call failed with response: %s", response.text)

        # Handle failures: either raise original exception or return None
        if raise_on_error:
            if response is None and last_exception:
                # Re-raise the original network/connection exception
                raise last_exception
            elif response is not None:
                # HTTP error - let requests handle it
                response.raise_for_status()
        
        # Original behavior - log warning, update fail count, and return None (for backward compatibility)
        _LOGGER.warning("API call returning None for URL: %s (fail_count: %d, response: %s)", 
                       url, self._fail_count, "None" if response is None else f"HTTP {response.status_code}")
        
        if self._fail_count == 5:
            self.__http_api_connected = False
        else:
            self._fail_count = self._fail_count + 1
        return None

    def disconnect(self):
        """Disconnect from cloud services and cleanup resources."""
        # Cleanup async task infrastructure
        if self._thread:
            self._queue.put([])
            
        if self._session:
            self._session.close()
        self.__http_api_connected = False
        self.__logged_in = False