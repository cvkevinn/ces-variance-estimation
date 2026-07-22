import requests
import json
import os

# from connectors import web
import ecb_certifi

from settings import EDP_WORK_DIR, REGISTRY_HOST_ACC, REGISTRY_HOST_PROD

width = 80
half_width = int(width / 2)


def api_validation(
    path, ignore_mandatory_att=False, print_json=False, print_output=True, env="acc"
) -> bool:
    """
    Submit the file to the FR web service and wait for validation

    Parameters
    ----------
    :param path: string to the location of the file.
    :param ignore_mandatory_att: If True the mandatory attributes missing is ignored. Default is False.
    :param print_json: If True the full json from the validation is returned. Default is False. If print_output is set
    to False the json will not be printed.
    :param print_output: If True the validation will be printed otherwise only the bool is returned.
    :param env: Environment can be either acceptance ['acc', 'acceptance', 'stg', 'staging'] or
    production ['prod', 'prd', 'production']. Default is acc.
    :return: bool, True if no errors and False if errors.
    """

    url_validate = _get_url(env) + "/ws/public/data/validate"
    print("File being checked: ", path, "FR url: ", url_validate)
    headers = {
        "Accept": "application/vnd.sdmx.structurespecificdata+xml;version=2.1",
        "Zip": "false",
        "Prior-Data-Dependent": f"{ignore_mandatory_att}",
    }
    result = requests.post(
        url=url_validate,
        headers=headers,
        files={"uploadFile": open(path, "rb")},
        verify=ecb_certifi.where(),
    )

    errors = _check_errors_exist(result.json())

    if print_output:
        _print_output(result, print_json)

    return errors

    # TODO use ecb-connectors instead for requests
    # session = web.Session()
    # res = session.get(url_validate, headers=headers, files={'uploadFile': open(path, 'rb')})


def api_validation_async(path, env="acc") -> str:
    """
    Submit the file to the FR web service and wait for validation

    Parameters
    ----------
    :param path: string to the location of the file.
    :param env: Environment can be either acceptance ['acc', 'acceptance', 'stg', 'staging'] or
    production ['prod', 'prd', 'production']. Default is acc.
    :return: str, the uid to identify the validation
    """

    url_validate = _get_url(env) + "/ws/public/data/load"
    print("File being checked: ", path, "FR url: ", url_validate)
    # headers = {"Prior-Data-Dependent": f"{ignore_mandatory_att}"}
    result = requests.post(
        url=url_validate,
        files={"uploadFile": open(path, "rb")},
        verify=ecb_certifi.where(),
    )
    print(result.json())
    uid = result.json()["uid"]
    return uid


def get_async_validation_result(
    uid, print_json=False, print_output=False, env="acc"
) -> bool:
    """
    This function print the validation after the async validation have been done.
    :param uid: The id that was returned from the api_validation_async call
    :param print_json: If True the full json from the validation is returned. Default is False. If print_output is set
    to False the json will not be printed.
    :param print_output: If True the validation will be printed otherwise only the bool is returned.
    :param env: Environment can be either acceptance ['acc', 'acceptance', 'stg', 'staging'] or
    production ['prod', 'prd', 'production']. Default is acc.
    :return: bool, True if no errors and False if errors.
    """

    url_validate = _get_url(env) + "/ws/public/data/loadStatus?uid=" + uid
    # headers = {"Prior-Data-Dependent": f"{ignore_mandatory_att}"}
    result = requests.get(url=url_validate, verify=ecb_certifi.where())

    errors = _check_errors_exist(result.json())

    if print_output:
        _print_output(result, print_json)

    return errors


def _print_output(result, print_json=False):
    """
    Print the output of the validation.
    :param result: This is the return value from the validation in json format.
    :param print_json: If True the full json from the validation is returned. Default is False.
    :return: bool. True if there are errors and False if not.
    """
    formatted_json = json.dumps(result.json(), indent=4)

    if print_json:
        print(formatted_json)
    else:
        _refine_output(result.json())


def _refine_output(result):
    """
    Print the output in a structured way
    :param result: This is the return value from the validation in json format.
    :return: None
    """
    if result["Errors"] and "Datasets" in result:
        print()
        for dataset in result["Datasets"]:
            print("Validation Errors".center(width, "-"))
            print()
            print("Series Keys in file:".rjust(half_width), dataset["KeysCount"])
            print("Observations in file:".rjust(half_width), dataset["ObsCount"])
            print(
                "Frequencies in file:".rjust(half_width),
                list(dataset["ReportedPeriods"].keys()),
            )
            print()
            for error_type in dataset["ValidationReport"]:
                print()
                print(error_type["Type"].center(width, "-"))
                for error in error_type["Errors"]:
                    print(
                        f"{error['ErrorCode']} ({error['Position']})".rjust(half_width),
                        ":",
                        error["Message"],
                    )
                print()
    elif result["Errors"] and "Error" in result:
        print(result["Error"])
    else:
        print("No errors found!")


def _check_errors_exist(result) -> bool:
    """
    Check if errors exist in the validation
    :param result: This is the return value from the validation in json format.
    :return: bool: True if errors were found and False otherwise.
    """
    if result["Errors"] and "Error" or result["Errors"] and "Datasets" in result:
        return True
    else:
        return False


ACC_ALIASES = {"acc", "acceptance", "staging", "stg"}
PROD_ALIASES = {"prod", "prd", "production"}


def _get_url(env):
    """Resolve an environment alias to its SDMX registry host (see settings.py)."""
    if env in ACC_ALIASES:
        return REGISTRY_HOST_ACC
    if env in PROD_ALIASES:
        return REGISTRY_HOST_PROD
    return ""


if __name__ == "__main__":
    file = str(EDP_WORK_DIR / "ces_aggregates_edp.csv.xml")
    print("testing with a file!" + file)

    # USE THIS FOR SYNC API CALL TEST
    res = api_validation(
        path=file,
        ignore_mandatory_att=True,
        print_json=False,
        print_output=True,
        env="acc",
    )
    print("There are errors: ", res)

    # USE THIS FOR ASYNC API CALL TEST
    # res = api_validation_async(path=file2, env='acc')
    # print(res)
    # res = api_validation_async(
    #     path='<path-to>/validate_file_with_fr/data/PAY1.sdmx', env='acc')
    #
    # print('-------------------------Get Validation result-------------------------------------')
    #
    # get_async_validation_result(res, print_json=True, print_output=True, env='acc')
