import json
import os
import re
import textwrap
import time
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from typing import Union

import httpx
from Levenshtein import distance
from dotenv import load_dotenv
from langchain_core.messages import BaseMessage
from langchain_core.messages.ai import AIMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompt_values import StringPromptValue
from langchain_core.prompts import ChatPromptTemplate

import src.strings as strings
from loguru import logger

from src.app_config import LLM_MODEL_TYPE, LLM_MODEL, PRICE_DICT

load_dotenv()


class AIModel(ABC):
    @abstractmethod
    def invoke(self, prompt: str) -> str:
        pass


class OpenAIModel(AIModel):
    """Получить доступ к модели OpenAI"""
    def __init__(self, api_key: str, llm_model: str):
        from langchain_openai import ChatOpenAI
        self.model = ChatOpenAI(model_name=llm_model, openai_api_key=api_key,
                                temperature=0.4)

    def invoke(self, prompt: str) -> BaseMessage:
        logger.debug("Успешно получен доступ к модели через OpenAI API")
        response = self.model.invoke(prompt)
        return response


class ClaudeModel(AIModel):
    """Получить доступ к модели Claude"""
    def __init__(self, api_key: str, llm_model: str) -> None:
        from langchain_anthropic import ChatAnthropic
        self.model = ChatAnthropic(model=llm_model, api_key=api_key,
                                   temperature=0.4)

    def invoke(self, prompt: str) -> BaseMessage:
        response = self.model.invoke(prompt)
        logger.debug("Успешно получен доступ к модели через Claude API")
        return response


class OllamaModel(AIModel):
    """Получить доступ к модели Ollama"""
    def __init__(self, llm_model: str, llm_api_url: str) -> None:
        from langchain_ollama import ChatOllama

        if len(llm_api_url) > 0:
            logger.debug(f"Используем Ollama с API URL: {llm_api_url}")
            self.model = ChatOllama(model=llm_model, base_url=llm_api_url)
        else:
            self.model = ChatOllama(model=llm_model)

    def invoke(self, prompt: str) -> BaseMessage:
        response = self.model.invoke(prompt)
        logger.debug("Успешно получен доступ к модели через Ollama API")
        return response

#gemini doesn't seem to work because API doesn't rstitute answers for questions that involve answers that are too short
class GeminiModel(AIModel):
    """Получить доступ к модели Gemini"""
    def __init__(self, api_key:str, llm_model: str):
        from langchain_google_genai import ChatGoogleGenerativeAI, HarmBlockThreshold, HarmCategory
        self.model = ChatGoogleGenerativeAI(model=llm_model, google_api_key=api_key,safety_settings={
        HarmCategory.HARM_CATEGORY_UNSPECIFIED: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DEROGATORY: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_TOXICITY: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_VIOLENCE: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUAL: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_MEDICAL: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE
        })

    def invoke(self, prompt: str) -> BaseMessage:
        response = self.model.invoke(prompt)
        logger.debug("Успешно получен доступ к модели через Gemini API")
        return response

class HuggingFaceModel(AIModel):
    """Получить доступ к модели Hugging Face"""
    def __init__(self, api_key: str, llm_model: str):
        from langchain_huggingface import HuggingFaceEndpoint, ChatHuggingFace
        self.model = HuggingFaceEndpoint(repo_id=llm_model, huggingfacehub_api_token=api_key,
                                   temperature=0.4)
        self.chatmodel=ChatHuggingFace(llm=self.model)

    def invoke(self, prompt: str) -> BaseMessage:
        response = self.chatmodel.invoke(prompt)
        logger.debug("Успешно получен доступ к модели через Hugging Face API")
        print(response,type(response))
        return response

class AIAdapter:
    """Класс для получения доступа к LLM моделям разных фирм через API"""
    def __init__(self, config: dict, api_key: str):
        self.model = self._create_model(config, api_key)

    def _create_model(self, config: dict, api_key: str) -> AIModel:
        llm_api_url = config.get('llm_api_url', "")

        logger.debug(f"Using {LLM_MODEL_TYPE} with {LLM_MODEL}")

        if LLM_MODEL_TYPE == "openai":
            return OpenAIModel(api_key, LLM_MODEL)
        elif LLM_MODEL_TYPE == "claude":
            return ClaudeModel(api_key, LLM_MODEL)
        elif LLM_MODEL_TYPE == "ollama":
            return OllamaModel(LLM_MODEL, llm_api_url)
        elif LLM_MODEL_TYPE == "gemini":
            return GeminiModel(api_key, LLM_MODEL)
        elif LLM_MODEL_TYPE == "huggingface":
            return HuggingFaceModel(api_key, LLM_MODEL)        
        else:
            raise ValueError(f"Неподдерживаемый тип модели: {LLM_MODEL_TYPE}")

    def invoke(self, prompt: str) -> str:
        return self.model.invoke(prompt)


class LLMLogger:
    """Класс для логирования всех событий, происходящих при работе с LLM"""
    def __init__(self, llm: Union[OpenAIModel, OllamaModel, ClaudeModel, GeminiModel]):
        self.llm = llm
        logger.debug(f"LLMLogger успешно инициализирован, используем LLM: {llm}")

    @staticmethod
    def log_request(prompts, parsed_reply: Dict[str, Dict]) -> None:
        logger.debug("Starting log_request method")
        logger.debug(f"Prompts received: {prompts}")
        logger.debug(f"Parsed reply received: {parsed_reply}")

        try:
            calls_log = os.path.join(
                Path("data_folder/output"), "open_ai_calls.json")
            logger.debug(f"Logging path determined: {calls_log}")
        except Exception as e:
            logger.error(f"Error determining the log path: {str(e)}")
            raise

        if isinstance(prompts, StringPromptValue):
            logger.debug("Prompts are of type StringPromptValue")
            prompts = prompts.text
            logger.debug(f"Prompts converted to text: {prompts}")
        elif isinstance(prompts, Dict):
            logger.debug("Prompts are of type Dict")
            try:
                prompts = {
                    f"prompt_{i + 1}": prompt.content
                    for i, prompt in enumerate(prompts.messages)
                }
                logger.debug(f"Prompts converted to dictionary: {prompts}")
            except Exception as e:
                logger.error(f"Error converting prompts to dictionary: {str(e)}")
                raise
        else:
            logger.debug("Prompts are of unknown type, attempting default conversion")
            try:
                prompts = {
                    f"prompt_{i + 1}": prompt.content
                    for i, prompt in enumerate(prompts.messages)
                }
                logger.debug(f"Prompts converted to dictionary using default method: {prompts}")
            except Exception as e:
                logger.error(f"Error converting prompts using default method: {str(e)}")
                raise

        try:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.debug(f"Current time obtained: {current_time}")
        except Exception as e:
            logger.error(f"Error obtaining current time: {str(e)}")
            raise

        try:
            token_usage = parsed_reply["usage_metadata"]
            output_tokens = token_usage["output_tokens"]
            input_tokens = token_usage["input_tokens"]
            total_tokens = token_usage["total_tokens"]
            logger.debug(f"Token usage - Input: {input_tokens}, Output: {output_tokens}, Total: {total_tokens}")
        except KeyError as e:
            logger.error(f"KeyError in parsed_reply structure: {str(e)}")
            raise

        try:
            model_name = parsed_reply["response_metadata"]["model_name"]
            logger.debug(f"Model name: {model_name}")
        except KeyError as e:
            logger.error(f"KeyError in response_metadata: {str(e)}")
            raise

        try:
            # рассчитать общую стоимость запроса
            prices = PRICE_DICT.get(LLM_MODEL, {"price_per_input_token": 1.5e-7, 
                                                "price_per_output_token": 6e-7})
            price_per_input_token = prices["price_per_input_token"]
            price_per_output_token = prices["price_per_output_token"]
            total_cost = (input_tokens * price_per_input_token) + \
                (output_tokens * price_per_output_token)
            logger.debug(f"Total cost calculated: {total_cost}")
        except Exception as e:
            logger.error(f"Error calculating total cost: {str(e)}")
            raise

        try:
            log_entry = {
                "model": model_name,
                "time": current_time,
                "prompts": prompts,
                "replies": parsed_reply["content"],
                "total_tokens": total_tokens,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_cost": total_cost,
            }
            logger.debug(f"Log entry created: {log_entry}")
        except KeyError as e:
            logger.error(f"Error creating log entry: missing key {str(e)} in parsed_reply")
            raise

        try:
            with open(calls_log, "a", encoding="utf-8") as f:
                json_string = json.dumps(
                    log_entry, ensure_ascii=False, indent=4)
                f.write(json_string + "\n")
                logger.debug(f"Log entry written to file: {calls_log}")
        except Exception as e:
            logger.error(f"Error writing log entry to file: {str(e)}")
            raise


class LoggerChatModel:
    def __init__(self, llm: Union[OpenAIModel, OllamaModel, ClaudeModel, GeminiModel]):
        self.llm = llm
        logger.debug(f"LoggerChatModel successfully initialized with LLM: {llm}")

    def __call__(self, messages: List[Dict[str, str]]) -> str:
        logger.debug(f"Entering __call__ method with messages: {messages}")
        while True:
            try:
                logger.debug("Attempting to call the LLM with messages")

                reply = self.llm.invoke(messages)
                logger.debug(f"LLM response received: {reply}")

                parsed_reply = self.parse_llmresult(reply)
                logger.debug(f"Parsed LLM reply: {parsed_reply}")

                LLMLogger.log_request(
                    prompts=messages, parsed_reply=parsed_reply)
                logger.debug("Request successfully logged")

                return reply

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTPStatusError encountered: {str(e)}")
                if e.response.status_code == 429:
                    retry_after = e.response.headers.get('retry-after')
                    retry_after_ms = e.response.headers.get('retry-after-ms')

                    if retry_after:
                        wait_time = int(retry_after)
                        logger.warning(
                            f"Rate limit exceeded. Waiting for {wait_time} seconds before retrying (extracted from 'retry-after' header)...")
                        time.sleep(wait_time)
                    elif retry_after_ms:
                        wait_time = int(retry_after_ms) / 1000.0
                        logger.warning(
                            f"Rate limit exceeded. Waiting for {wait_time} seconds before retrying (extracted from 'retry-after-ms' header)...")
                        time.sleep(wait_time)
                    else:
                        wait_time = 30
                        logger.warning(
                            f"'retry-after' header not found. Waiting for {wait_time} seconds before retrying (default)...")
                        time.sleep(wait_time)
                else:
                    logger.error(f"HTTP error occurred with status code: {e.response.status_code}, waiting 30 seconds before retrying")
                    time.sleep(30)

            except Exception as e:
                logger.error(f"Unexpected error occurred: {str(e)}")
                logger.info(
                    "Waiting for 30 seconds before retrying due to an unexpected error.")
                time.sleep(30)
                continue

    def parse_llmresult(self, llmresult: AIMessage) -> Dict[str, Dict]:
        logger.debug(f"Parsing LLM result: {llmresult}")

        try:
            if hasattr(llmresult, 'usage_metadata'):
                content = llmresult.content
                response_metadata = llmresult.response_metadata
                id_ = llmresult.id
                usage_metadata = llmresult.usage_metadata

                parsed_result = {
                    "content": content,
                    "response_metadata": {
                        "model_name": response_metadata.get("model_name", ""),
                        "system_fingerprint": response_metadata.get("system_fingerprint", ""),
                        "finish_reason": response_metadata.get("finish_reason", ""),
                        "logprobs": response_metadata.get("logprobs", None),
                    },
                    "id": id_,
                    "usage_metadata": {
                        "input_tokens": usage_metadata.get("input_tokens", 0),
                        "output_tokens": usage_metadata.get("output_tokens", 0),
                        "total_tokens": usage_metadata.get("total_tokens", 0),
                    },
                }
            else :  
                content = llmresult.content
                response_metadata = llmresult.response_metadata
                id_ = llmresult.id
                token_usage = response_metadata['token_usage']

                parsed_result = {
                    "content": content,
                    "response_metadata": {
                        "model_name": response_metadata.get("model", ""),
                        "finish_reason": response_metadata.get("finish_reason", ""),
                    },
                    "id": id_,
                    "usage_metadata": {
                        "input_tokens": token_usage.prompt_tokens,
                        "output_tokens": token_usage.completion_tokens,
                        "total_tokens": token_usage.total_tokens,
                    },
                }                  
            logger.debug(f"Parsed LLM result successfully: {parsed_result}")
            return parsed_result

        except KeyError as e:
            logger.error(
                f"KeyError while parsing LLM result: missing key {str(e)}")
            raise

        except Exception as e:
            logger.error(
                f"Unexpected error while parsing LLM result: {str(e)}")
            raise


class GPTAnswerer:
    def __init__(self, config, llm_api_key):
        self.job = None
        self.ai_adapter = AIAdapter(config, llm_api_key)
        self.llm_cheap = LoggerChatModel(self.ai_adapter)
        self.chains = {
            "personal_information": self._create_chain(strings.personal_information_template),
            "legal_authorization": self._create_chain(strings.legal_authorization_template),
            "work_preferences": self._create_chain(strings.work_preferences_template),
            "education_details": self._create_chain(strings.education_details_template),
            "experience_details": self._create_chain(strings.experience_details_template),
            "projects": self._create_chain(strings.projects_template),
            "availability": self._create_chain(strings.availability_template),
            "salary_expectations": self._create_chain(strings.salary_expectations_template),
            "certifications": self._create_chain(strings.certifications_template),
            "languages": self._create_chain(strings.languages_template),
            "interests": self._create_chain(strings.interests_template),
            "cover_letter": self._create_chain(strings.coverletter_template),
        }

    @property
    def job_description(self) -> Dict[str, str]:
        return self.job["description"]

    @staticmethod
    def find_best_match(text: str, options: list[str]) -> str:
        logger.debug(f"Finding best match for text: '{text}' in options: {options}")
        distances = [
            (option, distance(text.lower(), option.lower())) for option in options
        ]
        best_option = min(distances, key=lambda x: x[1])[0]
        logger.debug(f"Best match found: {best_option}")
        return best_option

    @staticmethod
    def _remove_placeholders(text: str) -> str:
        logger.debug(f"Removing placeholders from text: {text}")
        text = text.replace("PLACEHOLDER", "")
        return text.strip()

    @staticmethod
    def _preprocess_template_string(template: str) -> str:
        logger.debug("Preprocessing template string")
        return textwrap.dedent(template)

    def set_resume(self, resume) -> None:
        logger.debug(f"Setting resume: {resume}")
        self.resume = resume

    def set_job(self, job) -> None:
        logger.debug(f"Setting job: {job}")
        self.job = job
        self.job["summarize_job_description"] = "Job description" # self.summarize_job_description(self.job["description"]) !!!

    def set_resume_profile(self, resume_profile: dict) -> None:
        logger.debug(f"Setting job application profile: {resume_profile}")
        self.resume_profile = resume_profile

    def summarize_job_description(self, text: str) -> str:
        logger.debug(f"Summarizing job description: {text}")
        strings.summarize_prompt_template = self._preprocess_template_string(
            strings.summarize_prompt_template
        )
        prompt = ChatPromptTemplate.from_template(
            strings.summarize_prompt_template)
        chain = prompt | self.llm_cheap | StrOutputParser()
        output = chain.invoke({"text": text})
        logger.debug(f"Summary generated: {output}")
        return output

    def _create_chain(self, template: str) -> ChatPromptTemplate:
        logger.debug(f"Creating chain with template: {template}")
        prompt = ChatPromptTemplate.from_template(template)
        return prompt | self.llm_cheap | StrOutputParser()

    def answer_question_textual_wide_range(self, question: str) -> str:
        """Определить тему заданного вопроса и ответить на него"""
        logger.debug(f"Отвечаем на текстовый вопрос: {question}")
        # промпт модели для определение темы вопроса и ответа на него
        section_prompt = """You are assisting a bot designed to automatically apply for jobs on AIHawk. The bot receives various questions about job applications and needs to determine the most relevant section of the resume to provide an accurate response.

        For the following question: '{question}', determine which section of the resume is most relevant. 
        Respond with exactly one of the following options:
        - Personal information
        - Legal Authorization
        - Work Preferences
        - Education Details
        - Experience Details
        - Projects
        - Availability
        - Salary Expectations
        - Certifications
        - Languages
        - Interests

        Here are detailed guidelines to help you choose the correct section:

        1. **Personal Information**:
        - **Purpose**: Contains your basic contact details and online profiles.
        - **Use When**: The question is about how to contact you or requests links to your professional online presence.
        - **Examples**: Email address, phone number, AIHawk profile, GitHub repository, personal website.

        2. **Legal Authorization**:
        - **Purpose**: Details your work authorization status and visa requirements.
        - **Use When**: The question asks about your ability to work in specific countries or if you need sponsorship or visas.
        - **Examples**: Work authorization in EU and US, visa requirements, legally allowed to work.

        3. **Work Preferences**:
        - **Purpose**: Specifies your preferences regarding work conditions and job roles.
        - **Use When**: The question is about your preferences for remote work, relocation, and willingness to undergo assessments or background checks.
        - **Examples**: Remote work, in-person work, open to relocation.

        4. **Education Details**:
        - **Purpose**: Contains information about your academic qualifications and courses.
        - **Use When**: The question concerns your degrees, universities attended, and relevant coursework.
        - **Examples**: Degree, university, field of study.

        5. **Experience Details**:
        - **Purpose**: Details your professional work history and key responsibilities.
        - **Use When**: The question pertains to your job roles, responsibilities, achievements and technoligies that you used in previous positions.
        - **Examples**: Job positions, company names, key responsibilities, skills acquired.

        6. **Projects**:
        - **Purpose**: Highlights specific projects you have worked on.
        - **Use When**: The question asks about particular projects, their descriptions, or links to project repositories.
        - **Examples**: Project names, descriptions, links to project repositories.

        7. **Availability**:
        - **Purpose**: Provides information on your availability for new roles.
        - **Use When**: The question is about how soon you can start a new job or your notice period.
        - **Examples**: Notice period, availability to start.

        8. **Salary Expectations**:
        - **Purpose**: Covers your expected salary range.
        - **Use When**: The question pertains to your salary expectations or compensation requirements.
        - **Examples**: Desired salary range.

        9. **Certifications**:
            - **Purpose**: Lists your professional certifications or licenses.
            - **Use When**: The question involves your certifications or qualifications from recognized organizations.
            - **Examples**: Certification names, issuing bodies, dates of validity.

        10. **Languages**:
            - **Purpose**: Describes the languages you can speak and your proficiency levels.
            - **Use When**: The question asks about your language skills or proficiency in specific languages.
            - **Examples**: Languages spoken, proficiency levels.

        11. **Interests**:
            - **Purpose**: Details your personal or professional interests.
            - **Use When**: The question is about your hobbies, interests, or activities outside of work.
            - **Examples**: Personal hobbies, professional interests.

        Provide only the exact name of the section from the list above with no additional text.
        """
        prompt = ChatPromptTemplate.from_template(section_prompt)
        chain = prompt | self.llm_cheap | StrOutputParser()
        output = chain.invoke({"question": question})

        match = re.search(
            r"(Personal information|Legal Authorization|Work Preferences|Education "
            r"Details|Experience Details|Projects|Availability|Salary "
            r"Expectations|Certifications|Languages|Interests|Cover letter)",
            output, re.IGNORECASE)
        if not match:
            raise ValueError(
                "Не смогли определить тему вопроса.")

        section_name = match.group(1).lower().replace(" ", "_")
        resume_section = getattr(self.resume, section_name, None) or self.resume_profile.get(section_name)
        if resume_section is None:
            logger.error(
                f"Section '{section_name}' not found in either resume or resume_profile.")
            raise ValueError(f"Section '{section_name}' not found in either resume or resume_profile.")
        chain = self.chains.get(section_name)
        if chain is None:
            logger.error(f"Chain not defined for section '{section_name}'")
            raise ValueError(f"Chain not defined for section '{section_name}'")
        output = chain.invoke(
            {"resume_section": resume_section, "question": question})
        logger.debug(f"Question answered: {output}")
        return output
    
    def write_cover_letter(self) -> str:
        """Написать сопроводительное письмо"""
        chain = self.chains.get("cover_letter")
        output = chain.invoke(
            {"resume": self.resume, "job_description": self.job_description})
        logger.debug(f"Cover letter generated: {output}")
        return output
