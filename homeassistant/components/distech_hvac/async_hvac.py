# import requests
import base64
from datetime import datetime
import json
import logging

import aiohttp

from homeassistant.core import HomeAssistant

typeToUrl = {
    "analogValue": "analog-value",
    "analogInput": "analog-input",
    "analogOutput": "analog-output",
    "binaryValue": "binary-value",
    "binaryInput": "binary-input",
    "binaryOutput": "binary-output",
    "multiStateValue": "multi-state-value",
}


def distechMessageToBacnetProperty(message):
    rdict = {
        "property_type": message["type"],
        "instance": message["instance"],
        "property_name": message["property"],
    }
    if message.get("value"):
        rdict["value"] = message.get("value")
    if message.get("priority"):
        rdict["priority"] = message.get("priority")
    if message.get("arrayIndex"):
        rdict["arrayIndex"] = message.get("arrayIndex")
    return rdict


class bacnetProperty:
    def __init__(
        self,
        property_type: str,
        instance: int,
        property_name: str,
        value=None,
        priority=-1,
        arrayIndex=-1,
        static: bool = False,
        update_required: bool = True,
    ) -> None:
        self.objectType = property_type
        self.objectInstance = instance
        self.propertyName = property_name
        self.priority = priority
        self.arrayIndex = -1
        self.objectName = f"{self.objectType}_{self.objectInstance}"
        self.propertyValue = None
        self._set_value(value)
        self.writeValue = self.propertyValue
        self.static = static
        self.update_required = update_required
        self.write_required = False

    def _set_value(self, value):
        if (
            self.propertyName == "propertyList"
            and value is not None
            and type(value) is str
        ):
            self.propertyValue = [
                f"{x[0].lower()}{x[1:].replace(' ', '')}".strip()
                for x in value.strip("{}").split(",")
            ]
        else:
            self.propertyValue = value

    def export(self):
        return {
            "property_type": self.objectType,
            "instance": self.objectInstance,
            "property_name": self.propertyName,
            "value": self.propertyValue,
            "priority": self.priority,
            "arrayIndex": self.arrayIndex,
            "static": self.static,
            "update_required": self.update_required,
        }

    def update(self, value):
        self.writeValue = value
        self.write_required = True

    def request_read(self):
        if self.update_required:
            if self.static:
                self.update_required = False
            return {
                "type": self.objectType,
                "instance": self.objectInstance,
                "property": self.propertyName,
                "arrayIndex": self.arrayIndex,
            }
        return None

    def request_write(self):
        if self.write_required:
            self.propertyValue = self.writeValue
            self.write_required = False
            return {
                "type": self.objectType,
                "instance": self.objectInstance,
                "property": self.propertyName,
                "priority": self.priority,
                "value": self.writeValue,
            }
        return None


class bacnetObject:
    """Hold some information about a BACNet object.
    Can be populated with any/all information pulled out of the Distech controller.
    """

    bacnet_properties: dict[str, bacnetProperty]

    def __init__(
        self,
        name: str,
        href: str | None = None,
        properties: dict[str, str] | None = None,
    ) -> None:
        self.name = name
        self.type = name.split("_")[0]
        self.index = int(name.split("_")[-1])
        self.arrayIndex = -1
        if href is None:
            self.href = f"/api/rest/v1/protocols/bacnet/local/objects/{typeToUrl[self.type]}/{self.index}"
        else:
            self.href = href
        if not properties:
            properties = {
                "propertyList": {
                    "property_type": self.type,
                    "instance": self.index,
                    "property_name": "propertyList",
                    "static": True,
                },
                "objectName": {
                    "property_type": self.type,
                    "instance": self.index,
                    "property_name": "objectName",
                    "static": True,
                },
                "description": {
                    "property_type": self.type,
                    "instance": self.index,
                    "property_name": "description",
                    "static": True,
                },
            }
            # properties = ["objectName", "description", "presentValue"]
        self.bacnet_properties = {}
        for x in properties:
            self.bacnet_properties[x] = bacnetProperty(**properties[x])

    def initProperties(self, prop_dict: dict["str"]):
        for pname in prop_dict:
            self.addBacnetProperty(prop_dict[pname])

    def makePropertyWriteRequest(self, properties: list | None = None):
        request = []
        for bacnet_property in self.bacnet_properties.values():
            if properties is not None and bacnet_property.propertyName in properties:
                request.append(bacnet_property.request_write())
            else:  # bacnet_property.update_required or not bacnet_property.static:
                if (msg := bacnet_property.request_write()) is not None:
                    request.append(msg)
        return request

    def makePropertyReadRequest(
        self, properties: list | None = None, get_all: bool = False
    ):
        request = []
        if properties is None:
            properties = self.bacnet_properties.keys()
        for bacnet_property in self.bacnet_properties.values():
            if (
                properties is not None and get_all
            ):  # bacnet_property.propertyName in properties:
                if (msg := bacnet_property.request_read()) is not None:
                    request.append(msg)
            elif bacnet_property.update_required or not bacnet_property.static:
                if (msg := bacnet_property.request_read()) is not None:
                    request.append(msg)
        return request

    def addBacnetProperty(self, bacnet_property: dict["str"]):
        self.bacnet_properties[bacnet_property["property_name"]] = bacnetProperty(
            **bacnet_property
        )

    def export(self):
        odict = {
            "name": self.name,
            "href": self.href,
            "properties": {},
        }
        for k in self.bacnet_properties.values():
            odict["properties"][k.propertyName] = k.export()
        return odict

    def __str__(self):
        odict = {
            "object": self.name,
            "type": self.type,
            "href": self.href,
            "properties": {},
        }
        for k in self.bacnet_properties.values():
            odict["properties"][k.propertyName] = k.propertyValue
        return json.dumps(odict)


class eclypseCtrl:
    def __init__(self, ip, creds, hass: HomeAssistant, **kwargs) -> None:
        """yes, init."""
        self.apislug = "api/rest/v1"
        self.address = ip
        self._creds = creds
        self.hcreds = str(
            base64.b64encode(f"{creds['user']}:{creds['password']}".encode())
        )[2:-1]
        self.cookie = None
        self.logger = logging.getLogger(kwargs.get("log", "eclypseCtrl"))
        self.verifySsl = False
        self.session = None

        self.hass = hass

        self.bacnet_objects = {}
        self.bacnet_root = "protocols/bacnet/local/objects"
        self.bacnet_obj_trend = (
            self.bacnet_root
            + "/{objtype}/{objId}/trend?bySequenceNumber=true&start={startIdx}&end={endIdx}"
        )
        self.bacnet_obj_single = self.bacnet_root + "/{objtype}/{objId}"
        self.request_volume = 0
        self.request_time = 0
        self._session = aiohttp.ClientSession()

    def export(self):
        exp = {"ip": self.address, "creds": self._creds, "objects": {}}
        for obj in self.bacnet_objects.values():
            exp["objects"][obj.name] = obj.export()
        return exp

    async def close(self):
        await self._session.close()

    def _prepare_header(self, content=None, header: dict = None) -> dict:
        """Create a header dict object to make http requests. Deals with cookie and required content/post parameters.
        Accepts a dict to modify but generally it isn't needed.
        content is only required for POST requests and then only to establish content-length.
        """
        if (header_out := header) is None:
            header_out = {}
        if self.cookie is None:
            header_out["Authorization"] = f"Basic {self.hcreds}"
            self.logger.warning("No session, adding auth tokens to header")
        else:
            header_out["Cookie"] = self.cookie
        header_out["content-type"] = "application/json"
        if content is not None:
            header_out["content-length"] = str(len(str(content)))
        return header_out

    def _prepare_url(self, endpoint: str) -> str:
        """Formulate a url based on arbitrary sections of an REST endpoint provided."""
        url = ""
        endpoint = endpoint.strip("/")
        if not endpoint.startswith("https://"):
            url = "https://"
        if self.address not in endpoint:
            url = f"{url}{self.address}"
        if self.apislug not in endpoint:
            url = f"{url}/{self.apislug}"
        url = f"{url}/{endpoint}"
        self.logger.debug(f"Composed target URL: {url}")
        return url

    async def get(self, endpoint: str) -> (dict | None):
        """Perfrom HTTP GET at the endpoint or endpoint fragment provided."""
        return await self.parseHttpResult(
            await self._session.get(
                self._prepare_url(endpoint),
                headers=self._prepare_header(),
                ssl=self.verifySsl,
            )
        )

    async def postJson(self, endpoint: str, content: dict) -> (dict | None):
        """Perform HTTP POST at the endpoint or endpoint fragment provided. Content is expected to be formatted appropriately already."""
        if "write" in endpoint:
            self.logger.info(f"post request content: {content}")
        return await self.parseHttpResult(
            await self._session.post(
                self._prepare_url(endpoint),
                headers=self._prepare_header(content=content),
                ssl=self.verifySsl,
                json=content,
            )
        )

    async def parseHttpResult(self, result: aiohttp.ClientResponse) -> dict | None:
        """Evaluate HTTP result and return a JSON object if the request was successful. Logs the result and returns None if not."""
        if result.status == 200:
            if self.cookie is None:
                self.cookie = result.headers.get("Set-Cookie")
            return json.loads(await result.content.read())
        else:
            self.logger.error(
                f"Received HTTP error response code and message {result.status}: {await result.content.read()}"
            )

    async def updateObjectData(self):
        for propertyResult in await self.postRequestObjectProperties():
            prop = bacnetProperty(static=True, update_required=False, **propertyResult)
            self.logger.debug(prop)
            self.bacnet_objects[prop.objectName].bacnet_properties[
                prop.propertyName
            ] = prop
        # return bacnetObjects

    async def getObjectData(self):
        """Request all Bacnet objects at all endpoints."""
        bacnetObjects = await self.getRawObjectData()
        for propertyResult in await self.postRequestObjectProperties(bacnetObjects):
            prop = bacnetProperty(
                static=True,
                update_required=False,
                **distechMessageToBacnetProperty(propertyResult),
            )
            self.logger.debug(prop)
            bacnetObjects[prop.objectName].bacnet_properties[prop.propertyName] = prop
        return bacnetObjects

    async def getRawObjectData(
        self, types: list | None = None, use_known: bool = False
    ) -> dict[str, bacnetObject]:
        """Request bacnet objects of all types provided (or all by default)."""
        if not (bacnet_types := types):
            bacnet_types = [
                "analog-value",
                "analog-input",
                "analog-output",
                "binary-value",
                "binary-input",
                "binary-output",
                "multi-state-value",
            ]
        bacnetObjects = {}
        for btype in bacnet_types:
            rawObjectList = await self.get(f"{self.bacnet_root}/{btype}")
            for rawObject in rawObjectList:
                bacnetObjects[rawObject["name"]] = bacnetObject(
                    rawObject["name"],
                    None,
                    None,
                )
        return bacnetObjects

    def parseRawObjectData(self, bacnet_objects, json_message):
        return json_message

    async def postRequestObjectProperties(
        self,
        objects: dict[str, bacnetObject] | None = None,
        properties: list[str] | None = None,
        get_all: bool = False,
    ) -> dict:
        """Request provided properties of provided objects. By default, pull all known properties of all known objects."""
        content = []
        if not objects:
            objects = self.bacnet_objects
        for obj in objects.values():
            content += obj.makePropertyReadRequest(properties, get_all)

        if content:
            self.logger.debug(f"Requesting {len(content)} values from the controller")
            self.logger.debug(f"request: {content}")
            start = datetime.now()
            result = await self.postJson(
                endpoint=f"{self.bacnet_root}/read-property-multiple",
                content={"encode": "text", "propertyReferences": content},
            )
            # self.logger.info(
            #    f"Requested {len(content)} values. Execution time was {(datetime.now() - start).total_seconds()}"
            # )
            self.request_volume = len(content)
            self.request_time = (datetime.now() - start).total_seconds()
            self.readJsonIntoObjects(result)
            return result
        return {}

    def readJsonIntoObjects(self, message: dict) -> None:
        # prop is a dict with 4 elements formatted similar to the json read-property-multiple request
        for prop in message:
            self.logger.debug(f"Reading into objects: {prop}")
            instance = prop["instance"]
            # kp = prop["property"]
            value = prop["value"]
            for obj in self.bacnet_objects:
                if obj == f"{prop['type']}_{instance}":
                    self.logger.debug(
                        f"matched {obj}, setting key {prop['property']} = {value}"
                    )
                    self.bacnet_objects[obj].bacnet_properties[
                        prop["property"]
                    ].propertyValue = value
                    break


def convertPropertyString(properties: str) -> list:
    prop_list = []
    for prop in properties.strip("{}").split(","):
        prop_name = prop.replace(" ", "")
        prop_name = prop_name[0].lower() + prop_name[1:]
        prop_list.append(prop_name)
    return prop_list
