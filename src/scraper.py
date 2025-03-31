import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.select import Select
import pandas as pd
from datetime import datetime
import time

# URL base para consulta no DOU
BASE_URL_LISTAGEM = "https://www.in.gov.br/leiturajornal"

# XPath do botão "próxima página", caso presente
XPATH_NEXT_PAGE = "/html/body/div[1]/div/main/div[2]/div/div[2]/div/div/div/div[4]/section/div/div[2]/div/div[4]/div[2]/div/b[2]/span"


def configurar_driver():
    """Retorna uma instância do driver do Chrome."""
    options = webdriver.ChromeOptions()
    # options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(5)
    return driver


def baixar_pagina_listagem(data_consulta):
    """
    Acessa a página contendo a listagem de extratos para a data especificada e extrai os links
    dos extratos de nota de empenho da Seção 3 do DOU.
    Caso haja paginação, o código clica no botão de próxima página e agrega os links de todas as páginas.
    """
    driver = configurar_driver()
    url = f"{BASE_URL_LISTAGEM}?data={data_consulta}&secao=do3&ato=Extrato%20de%20Nota%20de%20Empenho"
    driver.get(url)
    time.sleep(3)
    all_links = []

    try:
        Select(driver.find_element(By.XPATH, '//*[@id="slcTipo"]')).select_by_value(
            "Extrato de Nota de Empenho"
        )

        while True:
            links_elements = driver.find_elements(
                By.XPATH,
                "//a[contains(translate(@href, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'extrato-de-nota-de-empenho')]",
            )
            for elem in links_elements:
                link = elem.get_attribute("href")
                if link and link not in all_links:
                    all_links.append(link)

            try:
                next_page_element = driver.find_element(By.XPATH, XPATH_NEXT_PAGE)
                if not next_page_element.is_enabled():
                    break
                next_page_element.click()
                time.sleep(3)
            except Exception as e:
                print("Nenhuma próxima página encontrada ou ocorreu um erro:", e)
                break

    except Exception as e:
        print("Não há extrato de nota de empenho publicado nessa data.", e)

    driver.quit()
    return all_links


def extrair_dados_texto(texto):
    """
    Utiliza regular expressions para extrair os dados do texto completo da página.
    Ajuste os padrões conforme os exemplos de notas de empenho.
    """
    dados = {}

    # UASG: Pode vir no título, ex.: "EXTRATO DE NOTA DE EMPENHO - UASG 390004"
    m = re.search(
        r"EXTRATO DE NOTA DE EMPENHO\s*-\s*UASG\s*(\d+)", texto, re.IGNORECASE
    )
    dados["UASG"] = m.group(1) if m else None

    # Nota de Empenho: "Nota de Empenho: 2025NE000056"
    m = re.search(r"Nota de Empenho:\s*([\w\dNE]+)", texto, re.IGNORECASE)
    dados["Nota de Empenho"] = m.group(1) if m else None

    # Nº Processo: "Nº Processo: 50000.023035/2024-71."
    m = re.search(r"Nº Processo:\s*([\d\./-]+)", texto, re.IGNORECASE)
    dados["Nº Processo"] = m.group(1) if m else None

    # Ata/Contrato/Dispensa de licitação: Pode vir integrado com outras informações
    m = re.search(r"(Dispensa|Contrat(?:o|a)|Ata).*?\.\s", texto, re.IGNORECASE)
    dados["Ata/Contrato/Dispensa de licitação"] = m.group(0).strip() if m else None

    # Contratante: "Contratante: SUBSECRETARIA PLAN.,ORC.E ADM.-ADMINISTRATIVO."
    m = re.search(r"Contratante:\s*([^\.]+)", texto, re.IGNORECASE)
    dados["Contratante"] = m.group(1).strip() if m else None

    # Contratado: "Contratado: 36.424.884/0001-59 - A L DA SILVA CONFECCOES" ou similar
    m = re.search(r"Contratado:\s*([^\.]+)", texto, re.IGNORECASE)
    dados["Contratado"] = m.group(1).strip() if m else None

    # Objeto: "Objeto: Contratação de serviço de confecção de materiais personalizados, ..."
    m = re.search(r"Objeto:\s*([^\.]+)", texto, re.IGNORECASE)
    dados["Objeto"] = m.group(1).strip() if m else None

    # Item: "Item 02." ou "Item 03."
    m = re.search(r"Item\s*(\d+)", texto, re.IGNORECASE)
    dados["Item"] = m.group(1).strip() if m else None

    # Vigência: "Vigência: 19/03/2025 a 31/12/2025"
    m = re.search(r"Vigência:\s*([^\.]+)", texto, re.IGNORECASE)
    dados["Vigência"] = m.group(1).strip() if m else None

    # Valor Total: "Valor Total Atualizado da NE: R$ 8.500,00"
    m = re.search(r"Valor Total.*?:\s*(R\$[\s\d\.,]+)", texto, re.IGNORECASE)
    dados["Valor Total"] = m.group(1).strip() if m else None

    # Data da assinatura: "Data de Assinatura: 19/03/2025" ou "Data da Emissão da Nota de Empenho: 25/03/2025"
    m = re.search(
        r"Data (?:de Assinatura|da Emissão da Nota de Empenho):\s*([\d/]+)",
        texto,
        re.IGNORECASE,
    )
    dados["Data da assinatura"] = m.group(1).strip() if m else None

    return dados


def extrair_dados_extrato(url):
    """
    Acessa a página do extrato individual, obtém o texto completo da página e extrai os dados utilizando
    a função 'extrair_dados_texto'.
    """
    driver = configurar_driver()
    driver.get(url)
    time.sleep(3)

    try:
        texto_completo = driver.find_element(By.TAG_NAME, "body").text
    except Exception as e:
        print(f"Erro ao obter o texto da página: {e}")
        texto_completo = ""

    driver.quit()

    dados = extrair_dados_texto(texto_completo)
    return dados


def salvar_para_excel(dados, data_execucao):
    """
    Recebe uma lista de dicionários cotendo os dados extraídos e os salva em um arquivo Excel.
    O nome do arquivo inicia com a data de execução no formato YYYYMMDD.
    """
    df = pd.DataFrame(dados)
    nome_arquivo = f"{data_execucao.strftime('%Y%m%d')}_extrato_notas_empenho.xlsx"
    df.to_excel(nome_arquivo, index=False)
    print(f"Arquivo salvo: {nome_arquivo}")


def baixar_e_processar_dados(data_execucao):
    """
    Função orquestradora:
      1. Converte a data para o formato esperado pela URL (DD-MM-AAAA).
      2. Baixa a página de listagem e extrai os links dos extratos, navegando por todas as páginas se necessário.
      3. Processa cada link, extrai os dados do texto e salva os resultados.
    """
    data_consulta = data_execucao.strftime("%d-%m-%Y")
    links = baixar_pagina_listagem(data_consulta)

    if not links:
        print("Nenhum link de extrato foi encontrado.")
        return

    todos_dados = []
    for link in links:
        if link.startswith("/"):
            link = "https://www.in.gov.br" + link
        print(f"Processando: {link}")
        dados = extrair_dados_extrato(link)
        if dados:
            todos_dados.append(dados)

    if todos_dados:
        salvar_para_excel(todos_dados, data_execucao)
    else:
        print("Nenhum dado foi extraído.")
