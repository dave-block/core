# import argparse
# import base64
# import json
# import logging

# import requests

# from homeassistant.core import HomeAssistant

# typeToUrl = {
#     "analogValue": "analog-value",
#     "analogInput": "analog-input",
#     "analogOutput": "analog-output",
#     "binaryValue": "binary-value",
#     "binaryInput": "binary-input",
#     "binaryOutput": "binary-output",
#     "multiStateValue": "multi-state-value",
# }


# class bacnetObject:
#     """Hold some information about a BACNet object.
#     Can be populated with any/all information pulled out of the Distech controller.
#     """

#     def __init__(self, name: str, href: str, vtype: str, properties: list = []) -> None:
#         self.name = name
#         self.type = vtype
#         self.index = int(name.split("_")[-1])
#         if href is None:
#             self.href = f"/api/rest/v1/protocols/bacnet/local/objects/{typeToUrl[self.type]}/{self.index}"
#         else:
#             self.href = href
#         if not properties:
#             self.properties = ["objectName", "description", "presentValue"]
#         else:
#             self.properties = properties
#         self.value_dict = {"type": self.type, "instance": self.index}

#     def buildRequest(self, properties: list = [], include_value: bool = False) -> list:
#         """Compose a list of dictionaries based on `properties`,
#         formatted for use in a read-multiple-properties POST request.
#         """
#         if not properties:
#             properties = self.properties
#         post = []
#         for property in properties:
#             post.append(
#                 {
#                     "type": self.type,
#                     "instance": self.index,
#                     f"{'priority' if include_value else 'arrayIndex'}": 1
#                     if include_value
#                     else -1,
#                     "property": property,
#                 }
#             )
#             if include_value:
#                 post[-1]["value"] = str(self.value_dict.get(property, ""))
#         return post

#     def setValue(self, property: str, value: str) -> None:
#         """Append a value to the internal dictionary."""
#         # Consider whether we should validate keys against the available list of properties, so we know it's consistent.
#         self.value_dict[property] = value

#     def __str__(self):
#         return f"bacnetObject(name={self.name}, href={self.href}, type={self.type}, index={self.index})"


# class eclypseCtrl:
#     def __init__(self, ip, creds, hass: HomeAssistant, start=True):
#         self.apislug = "api/rest/v1/"
#         self.curcli = ""
#         self.address = ip
#         self._creds = creds
#         self.hass = hass
#         self.hcreds = str(
#             base64.b64encode(f"{creds['user']}:{creds['password']}".encode())
#         )[2:-1]
#         self.cookie = None

#         self.bacnet_objects = []
#         self.bacnet_root = "protocols/bacnet/local/objects"
#         self.bacnet_obj_trend = (
#             self.bacnet_root
#             + "/{objtype}/{objId}/trend?bySequenceNumber=true&start={startIdx}&end={endIdx}"
#         )
#         self.bacnet_obj_single = self.bacnet_root + "/{objtype}/{objId}"

#         if start:
#             self.devinfo = self.get("info/device")
#             logger.info(self.devinfo["controllerName"])

#     def get(
#         self,
#         endpoint: str,
#         headers: dict = None,
#         verify: bool = False,
#         stub: bool = True,
#     ) -> dict | None:
#         """Generate a GET request for the specified endpoint."""
#         mid = "" if not stub else self.apislug
#         head = headers
#         if headers is not None:
#             if "Authorization" not in head and self.cookie is None:
#                 head["Authorization"] = f"Basic {self.hcreds}"
#             if "Cookie" not in head and self.cookie is not None:
#                 head["Cookie"] = self.cookie
#         else:
#             head = {}
#             if self.cookie is None:
#                 head["Authorization"] = f"Basic {self.hcreds}"
#                 logger.warning("No session started, authenticating")
#             else:
#                 head["Cookie"] = self.cookie

#         result = requests.get(
#             f"https://{self.address}/{mid}{endpoint.strip('/')}",
#             headers=head,
#             verify=verify,
#             timeout=5,
#         )
#         if result.status_code == 200:
#             if self.cookie is None:
#                 self.cookie = result.headers.get("Set-Cookie")
#             return json.loads(result.content.decode())

#     def postJson(
#         self,
#         endpoint: str,
#         content: dict,
#         headers: dict = None,
#         verify: bool = False,
#         stub: bool = True,
#     ) -> dict | None:
#         """Generate a POST request for the specified endpoint."""
#         mid = "" if not stub else self.apislug
#         if headers is not None:
#             if "Cookie" not in headers and self.cookie is not None:
#                 headers["Cookie"] = self.cookie
#             headers["content-type"] = "application/json"
#         else:
#             headers = {
#                 "Cookie": self.cookie,
#                 "content-type": "application/json",
#                 "content-length": str(len(str(content))),
#             }
#         result = requests.post(
#             f"https://{self.address}/{mid}{endpoint.strip('/')}",
#             headers=headers,
#             verify=verify,
#             json=content,
#             timeout=5,
#         )
#         logger.debug(f"Status code {result.status_code}")
#         if result.status_code == 200:
#             return json.loads(result.content.decode())
#         else:
#             logger.warning(f"Result of postJSON: {repr(result)}: {result.content}")

#     def populateObjects(self) -> None:
#         """Crawl the GET endpoints for the value types we care to pull and then compose a list of BACNet based on the results."""
#         bacnet_types = [
#             "analog-value",
#             "analog-input",
#             "analog-output",
#             "binary-value",
#             "binary-input",
#             "binary-output",
#             "multi-state-value",
#         ]
#         for btype in bacnet_types:
#             logger.info(f"Requesting objects for type {btype}")
#             valpoints = self.get(f"{self.bacnet_root}/{btype}")
#             for point in valpoints:
#                 vtype = f"{btype.split('-')[0]}"
#                 for x in btype.split("-")[1:]:
#                     vtype = f"{vtype}{x.capitalize()}"
#                 self.bacnet_objects.append(
#                     bacnetObject(point["name"], point["href"], vtype)
#                 )
#                 logger.debug(self.bacnet_objects[-1])

#     def populateAllObjectProperties(self) -> None:
#         logger.info(
#             f"Requesting properties for {len(self.bacnet_objects)} objects. Expected time ~{len(self.bacnet_objects)/2} seconds."
#         )
#         for object in self.bacnet_objects:
#             logger.debug(f"Requesting properties for {object.name}")
#             object.properties = [
#                 prop["name"]
#                 for prop in self.get(f"{object.href}/properties", stub=False)
#             ]
#             logger.debug(f"{object.name}: {object.properties}")

#     def postRequestObjectProperties(
#         self, objects: list = [], properties: list = []
#     ) -> dict:
#         content = []
#         if not objects:
#             objects = self.bacnet_objects
#         for object in objects:
#             content += object.buildRequest(properties)
#         logger.info(f"Requesting {len(content)} values from the controller.")
#         result = self.postJson(
#             endpoint=f"{self.bacnet_root}/read-property-multiple",
#             content={"encode": "text", "propertyReferences": content},
#         )
#         logger.info(result)
#         self.readJsonIntoObjects(result)
#         return result

#     def postSetObjectProperties(self, target: str, properties: dict):
#         object = bacnetObject(target, None, target.split("_")[0], properties.keys())
#         logger.debug(f"properties: {properties}")
#         for key in properties:
#             object.setValue(key, properties[key])
#         content = object.buildRequest(include_value=True)
#         logger.info(content)
#         result = self.postJson(
#             endpoint=f"{self.bacnet_root}/write-property-multiple",
#             content={"encode": "text", "propertyReferences": content},
#         )
#         logger.debug(result)
#         return result

#     def readJsonIntoObjects(self, message: dict) -> None:
#         if not message:
#             return
#         for (
#             prop
#         ) in (
#             message
#         ):  # prop is a dict with 4 elements formatted similar to the json read-property-multiple request
#             logger.debug(f"Reading into objects: {prop}")
#             prop["instance"]
#             key = prop["property"]
#             value = prop["value"]
#             for obj in self.bacnet_objects:
#                 if obj.name == f"{prop['type']}_{prop['instance']}":
#                     obj.setValue(key, value)
#                     break

#     def dumpObjects(self, include_properties: bool = False) -> dict:
#         result = {}
#         for obj in self.bacnet_objects:
#             result[obj.name] = obj.value_dict
#             if include_properties:
#                 result[obj.name]["properties"] = obj.properties
#         return result

#     def loadBacnetConfig(self, filename: str) -> None:
#         with open(filename) as f:
#             for line in f.read().split("\n"):
#                 if line:
#                     args = line.split(",", 3)
#                     props = []
#                     for prop in args[3].strip("[]").split(","):
#                         props.append(prop.strip(" '\""))
#                     self.bacnet_objects.append(bacnetObject(*args[0:3], props))

#     def saveBacnetConfig(self, filename: str) -> None:
#         with open(filename, "w") as f:
#             for object in self.bacnet_objects:
#                 f.write(
#                     f"{object.name},{object.href},{object.type},{object.properties}\n"
#                 )


# def convertPropertyString(properties: str) -> list:
#     prop_list = []
#     for prop in properties.strip("{}").split(","):
#         prop_name = prop.replace(" ", "")
#         prop_name = prop_name[0].lower() + prop_name[1:]
#         prop_list.append(prop_name)
#     return prop_list


# logger = logging.getLogger("hvac")
# if __name__ == "__main__":
#     parser = argparse.ArgumentParser(prog="hvacuum", description="hvac data dump")
#     parser.add_argument(
#         "--populate",
#         action="store_true",
#         help="Compose a full list of BACNet objects found at the bacnet/local/objects endpoint.",
#     )
#     parser.add_argument(
#         "--load",
#         help="Load a set of BACNet objects from a csv file specified.",
#         metavar="FILE",
#     )
#     parser.add_argument(
#         "--save",
#         help="Save a set of BACNet objects to a csv file specified.",
#         metavar="FILE",
#     )
#     parser.add_argument(
#         "--show-properties",
#         action="store_true",
#         help="Return the set of supported object properties along with the object values requested.",
#     )
#     parser.add_argument(
#         "--properties",
#         help="Comma-separated list of properties to request against known objects.",
#         default="objectName,description,presentValue",
#     )
#     parser.add_argument(
#         "--objects", help="Comma-separated list of objects to use instead of csv."
#     )
#     parser.add_argument(
#         "--request-values",
#         action="store_true",
#         help="Make a multi-value POST request against the controller using the loaded BACNet objects/properties.",
#     )
#     parser.add_argument(
#         "--write-values",
#         help="Make a multi-value post request from a list of key-value pairs in the format key1:value1,key2:value2,...",
#     )
#     parser.add_argument("--write-object")
#     parser.add_argument("--get-cnv-props", action="store_true")
#     parser.add_argument("--loglevel", default="info")
#     args = parser.parse_args()

#     if args.loglevel == "info":
#         logger.setLevel(logging.INFO)
#     elif args.loglevel == "debug":
#         logger.setLevel(logging.DEBUG)
#     logger.addHandler(logging.StreamHandler())
#     requests.packages.urllib3.disable_warnings()
#     ctl = eclypseCtrl(
#         "10.14.5.54", {"user": "onlogic_admin", "password": "P@ssword1234"}
#     )
#     if args.populate:
#         logger.info("Requesting all objects from the controller.")
#         ctl.populateObjects()
#         ctl.populateAllObjectProperties()
#         if args.save:
#             ctl.saveBacnetConfig(args.save)
#     elif args.load:
#         ctl.loadBacnetConfig(args.load)
#     elif args.objects:
#         for obj in args.objects.split(","):
#             ctl.bacnet_objects.append(bacnetObject(obj, None, obj.split("_")[0]))
#         if args.show_properties:
#             ctl.populateAllObjectProperties()
#     # ctl.postRequestObjectProperties()
#     if args.request_values:
#         res = ctl.postRequestObjectProperties(properties=args.properties.split(","))
#         print(
#             json.dumps(
#                 ctl.dumpObjects(include_properties=args.show_properties), indent=4
#             )
#         )

#     if args.write_values:
#         props = {}
#         for pair in args.write_values.split(","):
#             key, val = pair.split(":")
#             props[key] = val
#         res = ctl.postSetObjectProperties(args.write_object, props)

#     if args.get_cnv_props:
#         for obj in ctl.bacnet_objects:
#             res = ctl.postRequestObjectProperties(
#                 objects=[obj], properties=["propertyList"]
#             )
#             res = ctl.postRequestObjectProperties(
#                 objects=[obj], properties=convertPropertyString(res[0]["value"])
#             )  # properties=['propertyList'])
#             logger.info(json.dumps(res, indent=4))
#         # for x in res:
#         # 	logger.info(json.dumps(ctl.postRequestObjectProperties(properties=convertPropertyString(x['value'])), indent=4))
