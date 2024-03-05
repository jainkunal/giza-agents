import json
import logging
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import onnxruntime as ort
import requests
from giza import API_HOST
from giza.client import ApiClient, ModelsClient, VersionsClient
from giza.utils.enums import Framework, VersionStatus
from osiris.app import (
    create_tensor_from_array,
    deserialize,
    load_data,
    serialize,
    serializer,
)

from giza_actions.utils import get_deployment_uri


class GizaModel:
    """
    A class to manage the lifecycle and predictions of models using both local ONNX runtime sessions and
    remote deployments via the Giza SDK.

    Attributes:
        session (ort.InferenceSession | None): An ONNX runtime inference session for local model predictions.
        model_client (ModelsClient): Client to interact with the models endpoint of the Giza API.
        version_client (VersionsClient): Client to interact with the versions endpoint of the Giza API.
        api_client (ApiClient): General client for interacting with the Giza API.
        uri (str): The URI for making prediction requests to a deployed model.

    Args:
        model_path (Optional[str]): The file path to a local ONNX model. Defaults to None.
        id (Optional[int]): The unique identifier of the model in the Giza platform. Defaults to None.
        version (Optional[int]): The version number of the model in the Giza platform. Defaults to None.
        output_path (Optional[str]): The file path where the downloaded model should be saved. Defaults to None.

    Raises:
        ValueError: If the necessary combination of parameters is not provided.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        id: Optional[int] = None,
        version: Optional[int] = None,
        output_path: Optional[str] = None,
    ):
        if model_path is None and id is None and version is None:
            raise ValueError("Either model_path or id and version must be provided.")

        if model_path is None and (id is None or version is None):
            raise ValueError("Both id and version must be provided.")

        if model_path and (id or version):
            raise ValueError("Either model_path or id and version must be provided.")

        if model_path and id and version:
            raise ValueError(
                "Only one of model_path or id and version should be provided."
            )

        if model_path:
            self.session = ort.InferenceSession(model_path)
        elif id and version:
            self.model_client = ModelsClient(API_HOST)
            self.version_client = VersionsClient(API_HOST)
            self.api_client = ApiClient(API_HOST)
            self._get_credentials()
            self.version = self._get_version(id, version)
            print(self.version)
            self.session = None
            self.framework = self.version.framework
            self.uri = self._retrieve_uri(id, version)
            if output_path:
                self._download_model(id, version, output_path)

    def _retrieve_uri(self, model_id: int, version_id: int):
        """
        Retrieves the URI for making prediction requests to a deployed model.

        Args:
            model_id (int): The unique identifier of the model.
            version_id (int): The version number of the model.

        Returns:
            The URI for making prediction requests to the deployed model.
        """
        # Different URI per framework
        uri = get_deployment_uri(model_id, version_id)
        if self.framework == Framework.CAIRO:
            return f"{uri}/cairo_run"
        else:
            return f"{uri}/predict"

    def _get_version(self, model_id: int, version_id: int):
        """
        Retrieves the version of the model specified by model_id and version_id.

        Args:
            model_id (int): The unique identifier of the model.
            version_id (int): The version number of the model.

        Returns:
            The version of the model.
        """
        return self.version_client.get(model_id, version_id)

    def _download_model(self, model_id: int, version_id: int, output_path: str):
        """
        Downloads the model specified by model_id and version_id to the given output_path.

        Args:
            model_id (int): The unique identifier of the model.
            version_id (int): The version number of the model.
            output_path (str): The file path where the downloaded model should be saved.

        Raises:
            ValueError: If the model version status is not completed.
        """

        if self.version.status != VersionStatus.COMPLETED:
            raise ValueError(
                f"Model version status is not completed {self.version.status}"
            )

        print("ONNX model is ready, downloading! ✅")
        onnx_model = self.api_client.download_original(model_id, self.version.version)

        model_name = self.version.original_model_path.split("/")[-1]
        save_path = Path(output_path) / model_name

        with open(save_path, "wb") as f:
            f.write(onnx_model)

        print(f"ONNX model saved at: {save_path}")
        self.session = ort.InferenceSession(save_path)
        print("Model ready for inference with ONNX Runtime! ✅")

    def _get_credentials(self):
        """
        Retrieves and sets the necessary credentials for API access.
        """
        self.api_client.retrieve_token()
        self.api_client.retrieve_api_key()

    def predict(
        self,
        input_file: Optional[str] = None,
        input_feed: Optional[Dict] = None,
        verifiable: bool = False,
        fp_impl="FP16x16",
        output_dtype: str = "tensor_fixed_point",
        job_size: str = "M",
    ):
        """
        Makes a prediction using either a local ONNX session or a remote deployed model, depending on the
        instance configuration.

        Args:
            input_file (Optional[str]): The path to the input file for prediction. Defaults to None.
            input_feed (Optional[Dict]): A dictionary containing the input data for prediction. Defaults to None.
            verifiable (bool): A flag indicating whether to use the verifiable computation endpoint. Defaults to False.
            fp_impl (str): The fixed point implementation to use, when computed in verifiable mode. Defaults to "FP16x16".
            output_dtype (str): The data type of the result when computed in verifiable mode. Defaults to "tensor_fixed_point".

        Returns:
            A tuple (predictions, request_id) where predictions is the result of the prediction and request_id
            is the identifier of the prediction request if verifiable computation is used, otherwise None.

        Raises:
            ValueError: If required parameters are not provided or the session is not initialized.
        """
        try:
            if verifiable:
                if not self.uri:
                    raise ValueError("Model has not been deployed")

                # Non common arguments should be named parameters
                payload = self._format_inputs_for_framework(
                    input_file, input_feed, fp_impl=fp_impl, job_size=job_size
                )

                response = requests.post(self.uri, json=payload)

                try:
                    response.raise_for_status()
                except requests.exceptions.HTTPError as e:
                    logging.error(f"An error occurred in predict: {e}")
                    error_message = f"Deployment predict error: {response.text}"
                    logging.error(error_message)
                    raise e

                body = response.json()
                serialized_output = (
                    json.dumps(body["result"])
                    if self.framework == Framework.CAIRO
                    else body["result"]
                )
                request_id = (
                    json.dumps(body["request_id"])
                    if self.framework == Framework.CAIRO
                    else body["request_id"]
                )

                if self.framework == Framework.CAIRO:
                    logging.info("Serialized: ", serialized_output)

                    preds = self._parse_cairo_response(serialized_output, output_dtype)
                elif self.framework == Framework.EZKL:
                    preds = np.array(serialized_output[0])
                return (preds, request_id)

            else:
                if self.session is None:
                    raise ValueError("Session is not initialized.")
                if input_feed is None:
                    raise ValueError("Input feed is none")
                preds = self.session.run(None, input_feed)[0]
                return preds
        except Exception as e:
            logging.error(f"An error occurred in predict: {e}")
            raise e

    def _format_inputs_for_framework(self, *args, **kwargs):
        """
        Formats the inputs for a prediction request for a specific framework.

        Args:
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.
        """
        match self.framework:
            case Framework.CAIRO:
                return self._format_inputs_for_cairo(*args, **kwargs)
            case Framework.EZKL:
                return self._format_inputs_for_ezkl(*args, **kwargs)
            case _:
                # This should never happen
                raise ValueError(f"Unsupported framework: {self.framework}")

    def _format_inputs_for_cairo(
        self,
        input_file: Optional[str],
        input_feed: Optional[Dict],
        fp_impl,
        job_size: str,
    ):
        """
        Formats the inputs for a prediction request for OrionRunner.

        Args:
            input_file (Optional[str]): The path to the input file for prediction. Defaults to None.
            input_feed (Optional[Dict]): A dictionary containing the input data for prediction. Defaults to None.
            fp_impl (str): The fixed point implementation to use.

        Returns:
            dict: A dictionary representing the formatted inputs for the Cairo prediction request.
        """
        serialized = []

        if input_file is not None:
            serialized = serialize(input_file, fp_impl)

        if input_feed is not None:
            for name in input_feed:
                value = input_feed[name]
                if isinstance(value, np.ndarray):
                    tensor = create_tensor_from_array(value, fp_impl)
                    serialized.append(serializer(tensor))
                else:
                    serialized.append(serializer(tensor))

        return {"job_size": job_size, "args": " ".join(serialized)}
    
    def _format_inputs_for_ezkl(
        self, input_file: str, input_feed: Dict, job_size: str, *args, **kwargs
    ):
        """
        Formats the inputs for a prediction request for EZKL.

        Args:
            input_file (str): The path to the input file for prediction.
            input_feed (Dict): A dictionary containing the input data for prediction.

        Returns:
            dict: A dictionary representing the formatted inputs for the EZKL prediction request.
        """
        if input_file is not None:
            data = load_data(input_file).reshape([-1])
        elif input_feed is not None:
            match input_feed:
                case dict():
                    data = input_feed["input_data"]
                case list():
                    data = input_feed
                case np.ndarray():
                    data = input_feed.reshape([-1])
                case _:
                    raise ValueError(
                        "Invalid input_feed format. Must be a dictionary with 'input_data' containintg the data array."
                    )
        return {"input_data": [data], "job_size": job_size}

    def _parse_cairo_response(self, response, data_type: str):
        """
        Parses the response from a OrionRunner prediction request.

        Args:
            response (str): The serialized response from the Cairo prediction request.
            data_type (str): The data type to which the response should be deserialized.
            fp_impl (str): The fixed point implementation used.

        Returns:
            The deserialized prediction result.
        """
        return deserialize(response, data_type)
