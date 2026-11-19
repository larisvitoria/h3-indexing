<header id="header">
  <img src="docs/assets/header.png" alt="Cabeçalho do Documento" />
</header>

# **h3-indexing**

Fase 1 do projeto **Automatização da Agregação Hexagonal H3 para QGIS**: biblioteca Python + CLI que transforma camadas vetoriais de polígonos em uma grade hexagonal H3, redistribuindo atributos numéricos originais para os hexágonos gerados.

Esta biblioteca é o "motor" que, na Fase 2, será importado sem alterações pelo plugin `PyQGIS` (algoritmo do Processing Framework).

Além da CLI, o projeto inclui uma **interface web** (Streamlit) que envolve essa mesma biblioteca, permitindo executar o pipeline sem linha de comando.

## **Instalação**

Usando um ambiente virtual (recomendado), instale as dependências no modo de desenvolvimento:

```bash
cd h3-indexing
pip install -e ".[dev]"
```

Para usar a interface web (veja a seção [Interface Web](#interface-web-streamlit)), instale também as dependências específicas dela:

```bash
pip install streamlit geopandas folium streamlit-folium branca
```

## **Uso via CLI**

A seguir, um exemplo de execução da ferramenta via linha de comando:

```bash
h3-indexing \
    --input bairros.shp \
    --output resultado.gpkg \
    --resolution 8 \
    --attr populacao:extensivo \
    --attr renda_media:intensivo \
    --attr renda_total:ponderado:populacao
```

- `--input`: shapefile/GeoPackage de entrada.
- `--output`: arquivo de saída (`.shp`, `.gpkg` ou `.geojson`).
- `--resolution`: resolução H3, de 0 a 15.
- `--attr coluna:tipo`: um por atributo a redistribuir. `tipo` é
  `extensivo` (grandezas somáveis: população, domicílios, receita total) ou
  `intensivo` (médias/taxas: renda média, densidade populacional). Pode ser
  repetido.
- `--attr coluna:ponderado:coluna_peso`: razão entre dois atributos
  extensivos, calculada **depois** de repartir ambos pelos hexágonos (ex.:
  `renda_total:ponderado:populacao` → renda per capita por hexágono). O
  resultado é gravado em uma nova coluna `coluna_por_coluna_peso` (ex.:
  `renda_total_por_populacao`); para manter também o total, adicione
  `--attr renda_total:extensivo`. Hexágonos com peso zero ficam sem valor.
  Como o nome gerado costuma passar de 10 caracteres, prefira GeoPackage ou
  GeoJSON à Shapefile (que trunca nomes de colunas).

## **Interface Web (Streamlit)**

Para quem prefere não usar a linha de comando, o arquivo `app.py` oferece a
mesma funcionalidade da CLI em uma interface gráfica no navegador, chamando
internamente o mesmo `cli.run()` — sem duplicar a lógica de negócio.

### Como executar

```bash
streamlit run app.py
```

Isso abre a interface em `http://localhost:8501`.

### O que a interface oferece

- **Upload da camada de entrada**: aceita `.shp` (dentro de um `.zip` com
  `.shx`, `.dbf` e `.prj`), `.gpkg`, `.geojson` ou `.json`.
- **Configuração da resolução H3** por um slider (0 a 15).
- **Seleção dinâmica de colunas**: ao enviar o arquivo, a interface lê o
  esquema da camada e monta automaticamente a lista de colunas disponíveis
  para redistribuição — os atributos são escolhidos em uma lista suspensa
  (não digitados), o que evita erros de digitação e nomes de coluna
  inválidos. A lista é atualizada sempre que um novo arquivo é enviado.
- **Tipo do atributo**: para cada coluna escolhida, seleção entre
  `extensivo`, `intensivo` e `ponderado`. No tipo `ponderado` aparece um
  seletor extra, "Ponderar por", para escolher a coluna do denominador. Há
  aviso automático caso a mesma coluna de saída seja gerada mais de uma vez.
- **Prévia das fórmulas** (antes de gerar os hexágonos): uma aba por
  atributo configurado mostra a fórmula com os nomes reais das colunas e um
  simulador de um hexágono hipotético. Você escolhe até 4 polígonos do
  arquivo e, por sliders, quanto da área de cada um cai dentro do hexágono;
  a interface mostra a conta substituída passo a passo, o valor resultante e
  uma tabela com a contribuição de cada polígono. O cálculo usa o mesmo
  `distribute_attributes` do pipeline, então a prévia reflete exatamente o
  resultado real.
- **Formato de saída**: GeoPackage, Shapefile ou GeoJSON.
- **Execução do pipeline** com log em tempo real e tratamento de erros.
- **Download do resultado** ao final do processamento.
- **Visualização em mapa**: após a execução, os hexágonos gerados são
  exibidos em um mapa interativo (Folium, com tiles OpenStreetMap — sem
  necessidade de chave de API), coloridos de acordo com o atributo
  escolhido.

## **Fluxo de execução**

1. Leitura do arquivo de entrada.
2. Validação de geometria (correção com `buffer(0)` quando necessário) e CRS
   (reprojeção para EPSG:4326).
3. Geração dos hexágonos H3 cobrindo a extensão da camada, na resolução
   escolhida.
4. Sobreposição espacial (overlay) entre a camada original e a grade
   hexagonal.
5. Cálculo de distribuição de cada atributo, conforme sua natureza:
   - **Extensivo**: `valor_hex = Σ valor_i × (área_∩i / área_poli_i)`
   - **Intensivo**: `valor_hex = Σ(valor_i × área_∩i) / Σ área_∩i`
   - **Ponderado**: `valor_hex = Σ(valor_i × f_i) / Σ(peso_i × f_i)`, com
     `f_i = área_∩i / área_poli_i` — numerador e denominador são repartidos
     como extensivos e a divisão é feita no hexágono (razão das somas).
6. Exportação do resultado (Shapefile, GeoPackage ou GeoJSON).

Esse fluxo é o mesmo tanto na CLI quanto na interface web — a interface
apenas coleta os parâmetros graficamente e chama `cli.run()` internamente.

## **Estrutura**

```
h3-indexing/
├── src/h3_indexing/
│   ├── io.py            # leitura/escrita de shapefile, geopackage
│   ├── validation.py    # validação de geometria e CRS
│   ├── h3_grid.py       # geração da grade hexagonal H3
│   ├── overlay.py       # sobreposição espacial
│   ├── distribution.py  # cálculo de distribuição (extensivo/intensivo/ponderado)
│   └── cli.py           # interface de linha de comando
├── app.py               # interface web (Streamlit) sobre a CLI
├── .streamlit/
│   └── config.toml      # tema da interface web (cores, fontes, cantos)
├── tests/
├── pyproject.toml
└── README.md
```

## **Testes**

```bash
pytest
```

## **Próximos passos (Fase 2)**

Empacotar este módulo como dependência do plugin PyQGIS, expondo os mesmos
parâmetros (`--input`, `--resolution`, `--attr`, `--output`) como um
`QgsProcessingAlgorithm` na Toolbox de Processamento do QGIS, sem reescrever
a lógica de negócio aqui validada.