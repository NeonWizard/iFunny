import json, time, requests, threading

from ifunny import objects
from ifunny.util import methods, exceptions
from ifunny.objects import _mixin as mixin


class Chat(mixin.SendbirdMixin):
    """
    iFunny Chat object

    :param id: channel_url of the Chat. ``Chat.channel_url`` is aliased to this value, though ``id`` is more consistent with other mixin objects and how they update themselves.
    :param client: Client that the Chat belongs to
    :param data: A data payload for the Chat to pull from before requests
    :param paginated_size: number of items to get for each paginated request. If above the call type's maximum, that will be used instead

    :type id: str
    :type client: Client
    :type data: dict
    :type paginated_size: int
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.channel_url = self.id
        self._url = f"{self.client.sendbird_api}/group_channels/{self.id}"

    def __repr__(self):
        return self.title

    def _members_paginated(self, limit = None, next = None):
        limit = limit if limit else self.client.paginated_size

        data = methods.paginated_data_sb(f"{self._url}/members",
                                         "members",
                                         self.client.sendbird_headers,
                                         limit = limit,
                                         next = next)

        data["items"] = [
            ChatUser(member["user_id"],
                     self,
                     client = self.client,
                     sb_data = member) for member in data["items"]
        ]

        return data

    def _messages_paginated(self, limit = None, next = None):
        limit = limit if limit else self.client.paginated_size
        next = next if next else int(time.time() * 1000)

        params = {
            "prev_limit": limit,
            "message_ts": next,
            "include": False,
            "is_sdk": True,
            "reverse": True
        }

        messages = methods.request(
            "get",
            f"{self._url}/messages",
            params = params,
            headers = self.client.sendbird_headers)["messages"]

        next_ts = messages[::-1][0]["created_at"]
        items = [
            Message(message["message_id"], message["channel_url"], self.client)
            for message in messages
        ]

        return {"items": items, "paging": {"prev": None, "next": next_ts}}

    def _wait_to_set_frozen(self, wait, state, callback = None):
        time.sleep(wait)

        if self.fresh.frozen:
            self.frozen = state

        if callback:
            callback(self)

    # public methods

    @classmethod
    def by_link(cls, code, client = mixin.ClientBase(), **kwargs):
        """
        Get a chat from it's code.

        :param code: code of the chat to query. If this user does not exist, nothing will be returned
        :param client: the Client to bind the returned user object to

        :type code: str
        :type client: Client

        :returns: A Chat of the given code, if it exists
        :rtype: Chat, or None
        """
        try:
            data = methods.request(
                "get", f"{cls.api}/chats/channels/by_link/{code}",
                headers = client.headers
            )["data"]

            return cls(data["channel_url"], client = client, data = data, **kwargs)
        except exceptions.NotFound:
            return None

    def add_operator(self, user):
        """
        Add an operator toi a Chat

        :params user: operator to add

        :type user: User or ChatUser

        :returns: fresh list of this chat's operators
        :rtype: List<ChatUser>
        """
        data = {"operators": user.id}

        errors = {
            403: {
                "raisable": exceptions.Forbidden,
                "message": "You cannot modify the operators of this chat"
            }
        }

        methods.request(
            "put",
            f"{self.client.api}/chats/channels/{self.channel_url}/operators",
            data = data,
            headers = self.client.headers,
            errors = errors)

        return self.fresh.operators

    def remove_operator(self, user):
        """
        Remove an operator from a Chat

        :params user: operator to remove

        :type user: User or ChatUser

        :returns: fresh list of this chat's operators
        :rtype: List<ChatUser>
        """
        data = {"operators": user.id}

        errs = {
            403: {
                "raisable": exceptions.Forbidden,
                "message": "You cannot modify the operators of this chat"
            }
        }

        methods.request(
            "delete",
            f"{self.client.api}/chats/channels/{self.channel_url}/operators",
            data = data,
            headers = self.client.headers,
            errors = errors)

        return self.fresh.operators

    def add_admin(self, user):
        """
        Add an administrator to this Chat

        :param user: the user that should be an admin

        :type user: User or ChatUser

        :returs: self
        :rtype: Chat
        """
        return self.fresh

    def _add_admin(self, user):
        data = json.loads(self.get("data"))
        data["chatInfo"]["adminsIdList"] = [
            *self._data.get("adminsIdList", []), user.id
        ]

        data = {"data": json.dumps(data)}

        response = requests.put(self._url,
                                data = json.dumps(data),
                                headers = self.client.sendbird_headers)

        return self.fresh

    def remove_admin(self, user):
        """
        Remove an administrator from this Chat

        :param user: the user that should no longer be an admin

        :type user: User or ChatUser

        :returs: self
        :rtype: Chat
        """
        return self.fresh

    def _remove_admin(self, user):
        data = json.loads(self.get("data"))
        data["chatInfo"]["adminsIdList"] = [
            admin for admin in self._data.get("adminsIdList", [])
            if admin != user.id
        ]

        data = {"data": json.dumps(data)}

        response = requests.put(self._url,
                                data = json.dumps(data),
                                headers = self.client.sendbird_headers)

        return self.fresh

    def join(self):
        """
        Join this chat

        :returns: did this client join successfuly?
        :rtype: bool
        """
        response = requests.put(
            f"{self.client.api}/chats/channels/{self.channel_url}/members",
            headers = self.client.headers)

        return True if response.status_code == 200 else False

    def leave(self):
        """
        Leave this chat

        :returns: did this client leave successfuly?
        :rtype: bool
        """
        response = requests.delete(
            f"{self.client.api}/chats/channels/{self.channel_url}/members",
            headers = self.client.headers)

        return True if response.status_code == 200 else False

    def read(self):
        """
        Mark messages in a chat as read.

        :returns: self
        :rtype: Chat
        """
        if not self.client.socket.active:
            raise exceptions.ChatNotActive(
                "The chat socket has not been started")

        message_data = {
            "channel_url": self.channel_url,
            "req_id": self.client.next_req_id
        }

        self.client.socket.send(
            f"READ{json.dumps(message_data, separators = (',', ':'))}\n")
        return self

    def invite(self, user):
        """
        Invite a user or users to a chat.

        :param user: User or list<User> of invitees

        :type user: User, or list<User>

        :returs: self
        :rtype: Chat
        """

        data = json.dumps({
            "user_ids": [user.id]
            if isinstance(user, objects.User) else [u.id for u in users]
        })

        errors = {
            403: {
                "raisable": exceptions.Forbidden,
                "message": "You cannot invite users to this chat"
            }
        }

        methods.request("post",
                        f"{self._url}/invite",
                        data = data,
                        headers = self.client.sendbird_headers,
                        errors = errors)

        return self

    def kick(self, user):
        """
        Kick a member from a group

        :param user: User to kick
        :type user: User

        :return: self
        :rtype: Chat
        """
        data = {"members": user.id}

        errors = {
            403: {
                "raisable": exceptions.Forbidden,
                "message": "You must be an operator or admin to kick members"
            }
        }

        methods.request(
            "put",
            f"{self.client.api}/chats/channels/{self.channel_url}/kicked_members",
            data = data,
            headers = self.client.headers,
            errors = errors)

        return self

    def freeze(self, until = 0, callback = None):
        """
        Freeze a Chat, and set the update flag.

        :param until: time in seconds to wait to unfreeze. If 0, there will be no unfreezing
        :param callback: method to call when unfrozen, must accept single argument for Chat

        :type until: int
        :type callback: callable, or None

        :returs: self
        :rtype: Chat
        """

        self.frozen = True

        if until and isinstance(until, int):
            threading.Thread(target = self._wait_to_set_frozen,
                             args = [until, False],
                             kwargs = {
                                 "callback": callback
                             }).start()

        return self.fresh

    def unfreeze(self, until = 0, callback = None):
        """
        Freeze a Chat, and set the update flag.

        :param until: time in seconds to wait to unfreeze. If 0, there will be no unfreezing
        :param callback: method to call when unfrozen, must accept single argument for Chat

        :type until: int
        :type callback: callable, or None

        :returs: self
        :rtype: Chat
        """

        self.frozen = False

        if until and isinstance(until, int):
            threading.Thread(target = self._wait_to_set_frozen,
                             args = [until, True],
                             kwargs = {
                                 "callback": callback
                             }).start()

        return self.fresh

    def send_message(self, message, read = False):
        """
        Send a text message to a chat.

        :param message: text that you will send
        :param read: do we mark the chat as read?

        :type message: str
        :type read: bool

        :raises: ChatNotActive if the attached client has not started the chat socket

        :returns: self
        :rtype: Chat
        """
        if not self.client.socket.active:
            raise exceptions.ChatNotActive(
                "The chat socket has not been started")

        message_data = {
            "channel_url": self.channel_url,
            "message": message,
            #"req_id"        : self.client.next_req_id
        }

        self.client.socket.send(
            f"MESG{json.dumps(message_data, separators = (',', ':'))}\n")

        if read:
            self.read()

        return self

    def send_image_url(self,
                       image_url,
                       width = 780,
                       height = 780,
                       read = False):
        """
        Send an image to a chat from a url source.

        :param image_url: url where the image is located. This should point to the image itself, not a webpage with an image
        :param width: width of the image in pixels
        :param height: heigh of the image in pixels
        :param read: do we mark the chat as read?

        :type image_url: str
        :type width: int
        :type height: int
        :type read: bool

        :raises: ChatNotActive if the attached client has not started the chat socket

        :returns: self
        :rtype: Chat
        """
        if not self.client.socket.active:
            raise exceptions.ChatNotActive(
                "The chat socket has not been started")

        lower_ratio = min([width / height, height / width])
        type = "tall" if height >= width else "wide"
        mime = methods.determine_mime(image_url)

        response_data = {
            "channel_url":
            self.channel_url,
            "url":
            image_url,
            "name":
            f"botimage",
            "type":
            mime,
            "thumbnails": [{
                "url":
                image_url,
                "real_height":
                int(780 if type == "tall" else 780 * lower_ratio),
                "real_width":
                int(780 if type == "wide" else 780 * lower_ratio),
                "height":
                width,
                "width":
                height,
            }]
            #"req_id": self.client.next_req_id
        }

        self.client.socket.send(
            f"FILE{json.dumps(response_data, separators = (',', ':'))}\n")

        if read:
            self.read()

        return self

    # public generators

    @property
    def members(self):
        """
        :returns: generator to iterate through chat members
        :rtype: generator<ChatUser>
        """
        return methods.paginated_generator(self._members_paginated)

    @property
    def messages(self):
        """
        :returns: generator to iterate through chat messages
        :rtype: generator<Message>
        """
        return methods.paginated_generator(self._messages_paginated)

    # public properties

    @property
    def _data(self):
        _json = json.loads(self.get("data", "{}")).get("chatInfo", {})

        return _json

    @property
    def send(self):
        """
        :returns: this classes send_message method
        :rtype: function
        """
        return self.send_message

    @property
    def admins(self):
        """
        :returns: list of chat admins, if group
        :rtype: List<ChatUser>
        """
        data = self._data.get("adminsIdList", [])

        return [ChatUser(id, self, client = self.client) for id in data]

    @property
    def operators(self):
        """
        :returns: list of chat operators, if group
        :rtype: List<ChatUser>
        """
        data = self._data.get("operatorsIdList", [])

        return [ChatUser(id, self, client = self.client) for id in data]

    @property
    def title(self):
        """
        :returns: the title of this chat
        :rtype: str
        """
        _title = self.get("title")
        return _title if _title else self.get("channel").get("name")

    @title.setter
    def title(self, value):
        data = {"title": str(value), "description": self.description}

        response = requests.put(
            f"{self.client.api}/chats/channels/{self.channel_url}",
            data = data,
            headers = self.client.headers)
        self._update = True

    @property
    def name(self):
        """
        Alias for Chat.title
        """
        return self.title

    @property
    def created(self):
        """
        :returns: timestamp of this chats creation data
        :rtype: int
        """
        return self.get("created_at")

    @property
    def description(self):
        """
        :returns: admin defined description of the chat, if group
        :rtype: str, or None
        """
        _desc = self.get("description")
        return _desc if _desc else self._data.get("description")

    @description.setter
    def description(self, value):
        data = {"title": self.title, "description": str(value)}

        response = requests.put(
            f"{self.client.api}/chats/channels/{self.channel_url}",
            data = data,
            headers = self.client.headers)
        self._update = True

    @property
    def is_frozen(self):
        """
        :returns: is this chat frozen? Assumes False if attribute cannot be queried
        :rtype: bool
        """
        return self._data.get("chatInfo", {}).get("frozen")

    @is_frozen.setter
    def is_frozen(self, val):
        """
        Freeze or unfreeze a Chat
        """
        if not isinstance(val, bool):
            raise TypeError("Value should be bool")

        data = f"is_frozen={str(val).lower()}"

        response = requests.put(
            f"{self.client.api}/chats/channels/{self.channel_url}",
            headers = self.client.headers,
            data = data)

    @property
    def type(self):
        """
        :returns: the type of this group. Can be ``group``, ``opengroup``, ``chat``
        :rtype: str
        """
        return self.get("custom_type")

    @property
    def is_direct(self):
        """
        :returns: is this chat a private message chat?
        :rtype: bool
        """
        return self.type == "chat"

    @property
    def is_private(self):
        """
        :returns: is this chat a private group?
        :rtype: bool
        """
        return self.type == "group"

    @property
    def is_public(self):
        """
        :returns: is this chat a public group?
        :rtype: bool
        """
        return self.type == "opengroup"

    @property
    def member_count(self):
        """
        :returs: number of members in this chat
        :rtype: int
        """
        return self.get("member_count")

    # Authentication dependant properties

    @property
    def muted(self):
        """
        :returns: is this chat muted by the client?
        :rtype: bool
        """
        return self.get("is_muted")

    @property
    def user(self):
        """
        :returns: This clients ChatUser in this chat
        :rtype: ChatUser
        """
        return ChatUser(self.client.id, self, client = self.client)


class ChatUser(objects.User):
    """
    A User attatched to a chat.
    takes the same params as a User, with an extra set

    :param chat: Chat that this user is in
    :param sb_data: A sendbird data payload for the user to pull from before requests

    :type chat: Chat
    :type sb_data: dict
    """
    def __init__(self,
                 id,
                 chat,
                 *args,
                 client = mixin.ClientBase(),
                 sb_data = None,
                 **kwargs):
        super().__init__(id, client, *args, **kwargs)
        self._sb_url = chat._url
        self._sb_data_payload = sb_data
        self.__chat = chat

    def _sb_prop(self, key, default = None, force = False):
        if not self._sb_data.get(key, None) or force:
            self._update = True

        return self._sb_data.get(key, default)

    # public methods

    def kick(self):
        """
        Kick this member from a group

        :return: self
        :rtype: ChatUser
        """
        data = {"users": self.id}

        errors = {
            403: {
                "raisable": exceptions.Forbidden,
                "message": "You must be an operator or admin to kick members"
            }
        }

        methods.request(
            "put",
            f"{self.client.api}/chats/channels/{self.chat.channel_url}/kicked_members",
            data = data,
            headers = self.client.headers,
            errors = errors)

        return self

    @property
    def _sb_data(self):
        if self._update or self._sb_data_payload is None:
            self._update = False

            members = [
                member for member in self.chat._object_data.get("members")
                if member["user_id"] == self.id
            ]

            if not len(members):
                members = [{}]

            self._sb_data_payload = members[0]

        return self._sb_data_payload

    @property
    def state(self):
        """
        :returns: Is this member invited (pending join), or joined?
        :rtype: str
        """
        return self._sb_prop("state")

    @property
    def last_online(self):
        """
        :returns: timestamp of whne this user was last online
        :rtype: int
        """
        return self._sb_prop("last_seen_at")

    @property
    def online(self):
        """
        :returns: is this user online?
        :rtype: bool
        """
        return self._sb_prop("online", False)

    @property
    def chat(self):
        return self.__chat


class Message(mixin.SendbirdMixin):
    """
    Sendbird message object.
    Created when a message is recieved.

    :param data: message json, data after prefix in a sendbird websocket response
    :param client: client that the object belongs to

    :type data: dict
    :type client: Client
    """
    def __init__(self, id, channel_url, client, data = None):
        super().__init__(id, client, data = data)
        self.invoked = None

        self.__channel_url = None
        self.__chat = None
        self.__author = None
        self._url = f"{self.client.sendbird_api}/group_channels/{channel_url}/messages/{self.id}"

    def __repr__(self):
        return self.content if self.content else self.file_type

    def delete(self):
        """
        Delete a message sent by the client. This is exparamental, and may not work

        :returns: self
        :rtype: Message
        """
        if self.author != self.client.user:
            raise exceptions.NotOwnContent(
                "You cannot delete a message that does not belong to you")

        requests.delete(self._url)

        return self

    @property
    def author(self):
        """
        :returns: the author of this message
        :rtype: ChatUser
        """
        if not self.__author:
            self.__author = ChatUser(self.get("user").get("guest_id"),
                                     self.chat,
                                     client = self.client)

        return self.__author

    @property
    def chat(self):
        """
        :returns: Chat that this message exists in
        :rtype: Chat
        """
        if not self.__chat:
            self.__chat = Chat(self.channel_url, self.client)

        return self.__chat

    @property
    def content(self):
        """
        :returns: String content of the message
        :rtype: str
        """
        return self.get("message")

    @property
    def channel_url(self):
        """
        :returns: chat url for this messages chat
        :rtype: str
        """
        if not self.__channel_url:
            self.__channel_url = self.get("channel_url")

        return self.__channel_url

    @property
    def send(self):
        """
        :returns: the send() method of this messages chat for easy replies
        :rtype: function
        """
        return self.chat.send_message

    @property
    def send_image_url(self):
        """
        :returns: the send_image_url() method of this messages chat for easy replies
        :rtype: function
        """
        return self.chat.send_image_url

    @property
    def type(self):
        """
        :returns: type of message. Text messages will return type MESG, while files return the file mime
        :rtype: str
        """
        return self.get("type")

    @property
    def file_url(self):
        """
        :returns: message file url, if any
        :rtype: str, or None
        """
        if self.type == "MESG":
            return None

        return self.get("file").get("url")

    @property
    def file_data(self):
        """
        :returns: file binary data, if any
        :rtype: str, or None
        """
        if self.type == "MESG":
            return None

        return requests.get(self.file_url,
                            headers = self.client.sendbird_headers).content

    @property
    def file_type(self):
        """
        :returns: file type, if the message is a file
        :rtype: str, or None
        """
        if self.type == "MESG":
            return None

        return self.get("file").get("type")

    @property
    def file_name(self):
        """
        :returns: file name, if the message is a file
        :rtype: str, or None
        """
        if self.type == "MESG":
            return None

        return self.get("file").get("name")


class ChatInvite:
    """
    Chat update class.
    Created when an invite is recieved from the chat websocket.

    :param data: chat json, data after prefix in a sendbird websocket response
    :param client: client that the object belongs to

    :type data: dict
    :type client: Client
    """

    _status_codes = {10000: "accepted", 10020: "invite", 10022: "rejected"}

    def __init__(self, data, client):
        self.client = client
        self.__data = data

        self.__chat = None
        self.__channel_url = None
        self.__inviter = None
        self.__invitees = None
        self.__url = None

    @property
    def headers(self):
        return {
            "User-Agent": "jand/3.096",
            "Session-Key": self.client.sendbird_session_key
        }

    def accept(self):
        """
        Accept an incoming invitation, if it is from a user.
        If it is not, the method will do nothing and return None.

        :returns: Chat that was joined, or None
        :rtype: Chat, or None
        """
        if not self.inviter or self.client.user not in self.invitees:
            return None

        data = json.dumps({"user_id": self.client.id})

        methods.request("put",
                        f"{self.url}/accept",
                        headers = self.headers,
                        data = data)

        return self.chat

    def decline(self):
        """
        Decline an incoming invitation, if it is from a user.
        If it is not, the method will do nothing and return None.
        """
        if not self.inviter or self.client.user not in self.invitees:
            return None

        data = json.dumps({"user_id": self.client.id})

        methods.request("put",
                        f"{self.url}/decline",
                        headers = self.headers,
                        data = data)

        return self.chat

    @property
    def url(self):
        """
        :returns: the request url to the incoming Chat
        :rtype: str
        """
        if not self.__url:
            self.__url = f"{self.client.sendbird_api}/group_channels/{self.channel_url}"

        return self.__url

    @property
    def channel_url(self):
        """
        :returns: the url to the incoming Chat
        :rtype: str
        """
        if not self.__channel_url:
            self.__channel_url = self.__data["channel_url"]

        return self.__channel_url

    @property
    def chat(self):
        """
        :returns: the incoming Chat
        :rtype: Chat
        """
        if not self.__chat:
            self.__chat = Chat(self.channel_url, self.client)

        return self.__chat

    @property
    def inviter(self):
        """
        :returns: if this update is an invite, returns the inviter
        :rtype: User, or None
        """
        if not self.__inviter:
            inviter = self.__data["data"]["inviter"]

            if not inviter:
                return self.__inviter

            self.__inviter = ChatUser(inviter["user_id"],
                                      self.chat,
                                      client = self.client)

        return self.__inviter

    @property
    def invitees(self):
        """
        :returns: if this update is an invite, returns the invitees
        :rtype: list<User>, or None
        """
        if not self.__invitees:
            invitees = self.__data["data"]["invitees"]

            self.__invitees = [
                ChatUser(user["user_id"], self.chat, client = self.client)
                for user in invitees
            ]

        return self.__invitees

    @property
    def type(self):
        """
        :returns: the type of the incoming chat data
        :rtype: str
        """
        return self._status_codes.get(self.__data["cat"],
                                      f"unknown: {self.__data['cat']}")
