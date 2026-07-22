import requests
import ecb_certifi
import xml.etree.ElementTree as ET
from datetime import datetime
import xml.dom.minidom

from settings import EDP_WORK_DIR, REGISTRY_HOST_ACC, REGISTRY_HOST_PROD

namespaces = {
    "message": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message",
    "structure": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure",
    "xml": "http://www.w3.org/XML/1998/namespace",
    "common": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common",
}


ACC_ALIASES = {"acc", "acceptance", "staging", "stg"}
PROD_ALIASES = {"prod", "prd", "production"}


def _get_url(env):
    """Resolve an environment alias to its SDMX registry host (see settings.py)."""
    if env in ACC_ALIASES:
        return REGISTRY_HOST_ACC
    if env in PROD_ALIASES:
        return REGISTRY_HOST_PROD
    return ""


def add_extracted_element(response: str, extracted_time: str, file: str):
    tree = ET.fromstring(response)
    header = tree.find("message:Header", namespaces)

    # dataset_id = header.find("message:DataSetID", namespaces)
    # dataset_id.text = 'EWT'

    # action = header.find("message:DataSetAction", namespaces)
    # action.text = 'Replace'

    pos = 0
    for element in header:
        pos = pos + 1

        # Find DataSetID, after this element the Extracted element should be inserted
        if "DataSetID" in element.tag:
            # Create Extracted element
            ext = ET.Element("message:Extracted")
            now = datetime.now()
            ext.text = now.strftime("%Y-%m-%dT%H:%M:%S")

            # Insert Extracted element after DataSetID element at position (pos)
            header.insert(pos, ext)

    return ET.tostring(element=tree, encoding="unicode")


def transform_file(
    env: str,
    read_file: str,
    save_file: str,
    accept_format: str = "application/vnd.sdmx.structurespecificdata+xml;version=2.1",
    csv_delimiter: str = "",
    structure: str = "",
    sender_id: str = "4F0",
    receiver_id: str = "4F0",
    extracted_time: str = "",
):
    """
    :param env: The environment (FR) to be used as source
    :param read_file: Path and filename to the file that should be transformed
    :param save_file:  Path and filename where to save the output
    :param accept_format: The format it should be transformed to
    :param csv_delimiter: If the output format is CSV, define here the delimiter
    :param structure: URN to a DSD. Can be useful if the transformation not directly can find the DSD
    :param sender_id: Sender id to add to the header in an xml, e.g. 4F0, 4F4
    :param receiver_id: Receiver id tp add to the header in an xml file, e.g. 4F0
    :param extracted_time: Time in the format yyyy-mm-ddThh-mm-ss, if not provided current time will be used.
    :return: Transformed file
    """
    convert_to_xml = False

    headers = {"Accept": accept_format, "Content-Type": "application/xml"}

    if "xml" in accept_format:
        for prefix, uri in namespaces.items():
            ET.register_namespace(prefix, uri)
        headers["Dataset-Action"] = "Replace"

        convert_to_xml = True

    fr_url = _get_url(env)
    transform = "/ws/public/data/transform?prettyPrint=true"
    payload = open(read_file, "rb").read()

    if csv_delimiter and csv_delimiter.strip():
        headers["Data-Format"] = f"csv;delimiter{csv_delimiter}"

    if structure and structure.strip():
        headers["Structure"] = (
            f"urn:sdmx:org.sdmx.infomodel.datastructure.DataStructure={structure}(1.0)"
        )

    if sender_id and sender_id.strip():
        headers["Sender-Id"] = sender_id

    if receiver_id and receiver_id.strip():
        headers["Receiver-Id"] = receiver_id

    print("Header used in the transformation: " + str(headers))

    response = requests.post(
        fr_url + transform, headers=headers, data=payload, verify=ecb_certifi.where()
    )

    if response.status_code == 200:

        if convert_to_xml:
            temp_xml = add_extracted_element(response.text, extracted_time, save_file)
            xml_extracted = xml.dom.minidom.parseString(temp_xml)
            new_file = xml_extracted.toprettyxml()
        else:
            new_file = response.text

        with open(save_file, "w") as f:
            f.write(new_file)

        print(
            "file "
            + read_file
            + " is transformed to "
            + save_file
            + " using "
            + accept_format
        )
    else:
        print("something went wrong: " + str(response.status_code), response.text)

def update_release_time(xml_file: str, release_time: str) -> None:
    tree = ET.parse(xml_file)
    root = tree.getroot()
    for elem in root.findall('.//message:Extracted', namespaces):
        elem.text = release_time
    tree.write(xml_file, encoding='utf-8', xml_declaration=True)



if __name__ == "__main__":
    # CHOOSE ONE OF THE FORMATS BELOW FOR THE OUTPUT FILE

    # accept='application/vnd.sdmx.data+json;version=2.0.0' # Not supported yet in the FR
    # accept='application/vnd.sdmx.data+xml;version=3.0.0' # Not Supported yet in the FR 10.*
    # accept='application/vnd.sdmx.data+csv;version=2.0.0;labels=[id|name|both];timeFormat=[original|normalized];keys=[none|obs|series|both]' # Not supported yet in the FR

    # accept='application/vnd.sdmx.genericdata+xml;version=2.1'
    accept = "application/vnd.sdmx.structurespecificdata+xml;version=2.1"
    # accept='application/vnd.sdmx.generictimeseriesdata+xml;version=2.1'
    # accept='application/vnd.sdmx.structurespecifictimeseriesdata+xml;version=2.1'
    # accept='application/vnd.sdmx.data+json;version=1.0.0'
    # accept='application/vnd.sdmx.data+csv;version=1.0.0;labels=[id|both];timeFormat=[original|normalized]'
    # accept = 'application/vnd.sdmx.data+csv;version=1.0.0;labels=[id];timeFormat=[original]'

    file_to_read = str(EDP_WORK_DIR / "ces_aggregates_edp.csv")
    file_to_save = str(EDP_WORK_DIR / "ces_aggregates_edp.csv.xml")
    csv_delimiter = "comma"  # provide following options comma, tab, semicolon, space
    structure_ref = "ECB:ECB_CES1"  # OPTIONAL: If using CSV this needs to be provided. Provide agency and DSD Id sepearated with a :, e.g. ECB:ECB_EXR1, empty string if not needed

    # transform_file(env='acc', save_file=file_to_read, save_file=file_to_save, accept_format=accept,
    #                csv_delimiter=csv_delimiter, structure=structure)

    transform_file(
        env="acc",
        read_file=file_to_read,
        save_file=file_to_save,
        csv_delimiter=csv_delimiter,
        structure=structure_ref,
    )
