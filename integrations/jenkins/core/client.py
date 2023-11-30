from urllib.parse import urlencode, urlparse

import httpx
from typing import Any, AsyncGenerator

from loguru import logger

from core.utils import convert_timestamp_to_utc_dt, url_encode_str


class JenkinsClient:
    def __init__(
        self, jenkins_base_url: str, jenkins_user: str, jenkins_password: str
    ) -> None:
        self.jenkins_base_url = jenkins_base_url

        auth = (jenkins_user, jenkins_password)
        self.client = httpx.AsyncClient(auth=auth)

    async def get_jobs(self) -> AsyncGenerator[list[dict[str, Any]], None]:
        per_page = 100
        page = 0
        logger.info("Getting jobs from Jenkins")

        try:
            while True:
                # Parameters for pagination
                params = {
                    "tree": f"jobs[name,url,description,displayName,fullDisplayName,fullName]"
                }
                encoded_params = urlencode(params)

                job_response = await self.client.get(
                    f"{self.jenkins_base_url}/api/json?{encoded_params}"
                )
                job_response.raise_for_status()
                jobs = job_response.json()["jobs"]

                # If there are no more jobs, exit the loop
                if not jobs:
                    break

                logger.info(f"Got {len(jobs)} jobs from Jenkins")

                # put data in event-like json schema
                # makes blueprint mapping easy
                transformed = [
                    {
                        "type": "item.updated",
                        "data": job,
                        "url": urlparse(job.get("url")).path.lstrip(
                            "/"
                        ),  # since blueprint expects path rather host
                        "fullUrl": job.get("url"),
                        "time": job.get("timestamp"),
                    }
                    for job in jobs
                ]

                yield transformed
                page += 1

                if len(jobs) < per_page:
                    break
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error with status code: {e.response.status_code} and response text: {e.response.text}"
            )
            raise
        except httpx.HTTPError as e:
            logger.error(f"HTTP occurred while fetching Jenkins data {e}")
            raise

    async def get_builds(self, job_name: str) -> list[dict[str, Any]]:
        logger.info(f"Getting builds from Jenkins for job {job_name}")
        try:
            params = {
                "tree": f"builds[id,number,url,result,duration,timestamp,displayName,fullDisplayName]"
            }
            encoded_params = urlencode(params)

            build_response = await self.client.get(
                f"{self.jenkins_base_url}/job/{job_name}/api/json?{encoded_params}"
            )
            build_response.raise_for_status()
            builds = build_response.json().get("builds", [])
            logger.info(f"Got {len(builds)} builds from Jenkins for job {job_name}")

            # put data in event-like json schema
            # makes blueprint mapping easy
            transformed_builds = [
                {
                    "type": "run.finalize",
                    "source": url_encode_str(f"job/{job_name}/"),
                    "url": build.get("url", None),
                    "data": {
                        **build,
                        "timestamp": convert_timestamp_to_utc_dt(build.get("timestamp")),
                    },
                }
                for build in builds
            ]
            return transformed_builds
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error with status code: {e.response.status_code} and response text: {e.response.text}"
            )
            raise
        except httpx.HTTPError as e:
            logger.error(f"HTTP occurred while fetching Jenkins data {e}")
            raise
        
