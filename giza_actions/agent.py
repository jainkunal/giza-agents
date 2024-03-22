import logging
import os
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Optional, Tuple, Union

from ape import Contract, accounts, networks
from ape.exceptions import NetworkError
from giza import API_HOST
from giza.client import EndpointsClient, JobsClient, ProofsClient
from giza.schemas.jobs import Job, JobCreate, JobList
from giza.schemas.proofs import Proof
from giza.utils.enums import JobKind, JobSize, JobStatus

from giza_actions.model import GizaModel

logger = logging.getLogger(__name__)

class GizaAgent(GizaModel):
    """
    A blockchain AI agent that helps users put their Actions on-chain. Uses Ape framework and GizaModel to verify a model proof off-chain, sign it with the user's account, and send results to a select EVM chain to execute code.

    Attributes:
        model (GizaModel): The model that this deployer uploads proofs for. This model must have the following fields: id, version, orion_runner_service_url in order to work. This is because all on-chain models require a proof to be generated by Orion Runner.
        inference: The result of the GizaModel inference
        request_id: The request_id of the proof to fetch from the GCP
        proof: The proof from GCP that we will use to verify, sign, and send along with inference data
        

    Methods:
        infer: Runs model inference and retrieves the model output
        get_model_data: retrieves the proof from GCP given the request_id, version_id, endpoint_id, and internal model_id
        generate_calldate: generates calldata for a given smart contract function
        verify: verifies the proof locally
        deploy: verifies the proof, then calls the smart contract with calldata from inference
    """

    # TODO: (GIZ 502) Find a way to abstract away the chain_id to just a string with the chain name
    def __init__(
        self,
        id: int,
        version_id: int,
        contract_address: str,
        chain: str,
        account: str,
        **kwargs,
    ):
        """
        Args:
            model_id (int): The ID of the model.
            version_id (int): The version of the model.
            contract_address (str): The address of the contract.
            chain_id (int): The ID of the blockchain network.
            **kwargs: Additional keyword arguments.
        """
        super().__init__(id=id, version=version_id, **kwargs)
        self.contract_address = contract_address
        self.chain = chain
        self.account = account

        # Useful for testing
        network_parser: Callable = kwargs.get(
            "network_parser", networks.parse_network_choice
        )

        try:
            self._provider = network_parser(self.chain)
        except NetworkError:
            logger.error(f"Chain {self.chain} not found")
            raise ValueError(f"Chain {self.chain} not found")

        self._check_passphrase_in_env()

    def _check_passphrase_in_env(self):
        """
        Check if the passphrase is in the environment variables.
        """
        if f"{self.account.upper()}_PASSPHRASE" not in os.environ:
            logger.error(
                f"Passphrase for account {self.account} not found in environment variables. Passphrase must be stored in an environment variable named {self.account.upper()}_PASSPHRASE."
            )
            raise ValueError(
                f"Passphrase for account {self.account} not found in environment variables"
            )

    @contextmanager
    def execute(self):
        """
        Execute the agent in the given ecosystem. Return the contract instace so the user can execute it.

        Args:
            ecosystem: The ecosystem to execute the agent in.
        """
        logger.debug("Provider configured")
        with self._provider:
            self._account = accounts.load(self.account)
            logger.debug("Account loaded")
            self._account.set_autosign(
                True, passphrase=os.getenv(f"{self.account.upper()}_PASSPHRASE")
            )
            logger.debug("Autosign enabled")
            with accounts.use_sender(self._account):
                yield Contract(self.contract_address)

    def predict(
        self,
        input_file: Optional[str] = None,
        input_feed: Optional[Dict] = None,
        verifiable: bool = False,
        fp_impl="FP16x16",
        custom_output_dtype: Optional[str] = None,
        job_size: str = "M",
    ) -> Union["AgentResult", Tuple[Any, str]]:
        """
        Runs a round of inference on the model and saves the result.
        
        Args:
            input_file: The input file to use for inference
            input_feed: The input feed to use for inference
            job_size: The size of the job to run
        """
        result = super().predict(
            input_file=input_file,
            input_feed=input_feed,
            verifiable=verifiable,
            fp_impl=fp_impl,
            custom_output_dtype=custom_output_dtype,
            job_size=job_size,
        )

        self.verifiable = verifiable

        if not verifiable:
            logger.warning(
                "Inference is not verifiable. No request ID was returned. No proof will be generated."
            )
            return result

        pred, request_id = result
        return AgentResult(
            input=input_feed,
            request_id=request_id,
            result=pred,
            endpoint_id=self.endpoint_id,
            agent=self,
        )


class AgentResult:
    """
    A class to represent the result of an agent's inference.
    """

    def __init__(
        self,
        input: Any,
        request_id: str,
        result: Any,
        agent: GizaAgent,
        endpoint_client: EndpointsClient = EndpointsClient(API_HOST),
        jobs_client: JobsClient = JobsClient(API_HOST),
        proofs_client: ProofsClient = ProofsClient(API_HOST),
        **kwargs,
    ):
        """
        Args:
            input (list): The input to the agent.
            request_id (str): The request ID of the proof.
            value (int): The value of the inference.
        """
        self.input: Any = input
        self.request_id: str = request_id
        self._value: Any = result
        self.verified: bool = False
        self._endpoint_client = endpoint_client
        self._jobs_client = jobs_client
        self._proofs_client = proofs_client
        self._agent: GizaAgent = agent
        self._proof_job: Job = self._get_proof_job(self._endpoint_client)
        self._verify_job: Optional[Job] = None
        self._timeout: int = kwargs.get("timeout", 600)
        self._poll_interval: int = kwargs.get("poll_interval", 10)
        self._proof: Proof = None

    def __repr__(self) -> str:
        return f"AgentResult(input={self.input}, request_id={self.request_id}, value={self._value})"

    def _get_proof_job(self, client: EndpointsClient) -> Job:
        """
        Get the proof job.
        """

        jobs: JobList = client.list_jobs(self._agent.endpoint_id)
        for job in jobs.root:
            if job.request_id == self.request_id:
                return job
        raise ValueError(f"Proof job for request ID {self.request_id} not found")

    @property
    def value(self):
        """
        Get the value of the inference.
        """
        if self.verified:
            return self._value
        self._verify()
        return self._value

    def _verify(self):
        """
        Verify the proof. Check for the proof job, if its done start the verify job, then wait for verification.
        """
        self._wait_for_proof(self._jobs_client, self._timeout, self._poll_interval)
        self._verify_job = self._start_verify_job(self._jobs_client)
        self._wait_for_verify(self._jobs_client, self._timeout, self._poll_interval)
        self.verified = True

    def _wait_for_proof(
        self, client: JobsClient, timeout: int = 600, poll_interval: int = 10
    ):
        """
        Wait for the proof job to finish.
        """
        self._wait_for(self._proof_job, client, timeout, poll_interval, JobKind.PROOF)
        self._proof = self._endpoint_client.get_proof(
            self._agent.endpoint_id, self._proof_job.request_id
        )

    def _start_verify_job(self, client: JobsClient) -> Job:
        """
        Start the verify job.
        """
        job_create = JobCreate(
            size=JobSize.S,
            framework=self._agent.framework,
            model_id=self._agent.model_id,
            version_id=self._agent.version_id,
            proof_id=self._proof.id,
            kind=JobKind.VERIFY,
        )
        verify_job = client.create(job_create, trace=None)
        logger.info(f"Verify job created with ID {verify_job.id}")
        return verify_job

    def _wait_for_verify(
        self, client: JobsClient, timeout: int = 600, poll_interval: int = 10
    ):
        """
        Wait for the verify job to finish.
        """
        self._wait_for(self._verify_job, client, timeout, poll_interval, JobKind.VERIFY)

    def _wait_for(
        self,
        job: Job,
        client: JobsClient,
        timeout: int = 600,
        poll_interval: int = 10,
        kind: JobKind = JobKind.VERIFY,
    ):
        """
        Wait for a job to finish.

        Args:
            job (Job): The job to wait for.
            client (JobsClient): The client to use.
            timeout (int): The timeout.
            poll_interval (int): The poll interval.
            kind (JobKind): The kind of job.

        Raises:
            ValueError: If the job failed.
            TimeoutError: If the job timed out.
        """
        start_time = time.time()
        wait_timeout = start_time + float(timeout)

        while True:
            now = time.time()
            if job.status == JobStatus.COMPLETED:
                logger.info(f"{str(kind).capitalize()} job completed")
                return
            elif job.status == JobStatus.FAILED:
                logger.error(f"{str(kind).capitalize()} job failed")
                raise ValueError(f"{str(kind).capitalize()} job failed")
            elif now > wait_timeout:
                logger.error(f"{str(kind).capitalize()} job timed out")
                raise TimeoutError(f"{str(kind).capitalize()} job timed out")
            else:
                job = client.get(job.id, params={"kind": kind})
                logger.info(
                    f"{str(kind).capitalize()} job is still running, elapsed time: {now - start_time}"
                )
            time.sleep(poll_interval)
