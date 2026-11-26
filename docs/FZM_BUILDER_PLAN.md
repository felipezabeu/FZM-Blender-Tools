# FZM Builder — plano de execução e handoff

> Criado em 2026-11-24. Status: PRIMEIRA ENTREGA DE DESENVOLVIMENTO / FASE A. Requisitos aprovados pelo proprietário para iniciar desenvolvimento. Atualizar este arquivo conforme a execução; não declarar etapas concluídas sem evidência.

## 0. Leia primeiro — instrução para a conta Business / executor

O objetivo é criar uma derivação do Home Builder 5 para o fluxo de reformas da FZM, sem reconstruir funcionalidades que já funcionam. Este documento é a especificação de desenvolvimento, não um relatório de implementação.

- Repositório: https://github.com/felipezabeu/FZM-Blender-Tools
- Branch existente: https://github.com/felipezabeu/FZM-Blender-Tools/tree/dev/fzm-builder
- Upstream: https://github.com/CreativeDesigner3D/home_builder_5
- Baseline: tag v5.1.2, commit `f345c1710161a4d09149d8ec7b610d0c6f2a9d5e`. Confirmar também a versão realmente instalada no computador do proprietário; 5.1.2 é baseline de desenvolvimento escolhida, não confirmação da versão do add-on instalado.
- Blender alvo: 5.1.2, Windows para uso interativo e Linux headless para testes.
- O repositório é público. Não incluir credenciais, dados de clientes, projetos privados, swatches sem licença ou arquivos pessoais.
- Usar o executor que tenha Git completo e Blender real. Preferência: Codex CLI/app para implementação/testes, Astra para revisão de arquitetura quando a cota justificar. Hermes via OpenAI Codex OAuth não é Codex CLI. Não criar agentes, bridges ou infraestrutura nova.
- Autorizado: trabalhar na branch de desenvolvimento, implementar e testar em cópias isoladas. Não fazer merge em main, publicar no índice de produção, desinstalar Home Builder ou modificar arquivos .blend reais da biblioteca FZM sem validação e autorização específica.
- Priorizar entregas pequenas verificáveis. Se uma dependência impedir a execução, registrar o bloqueio e avançar apenas em trabalho independente. Não substituir resultados por planos repetidos; produzir código, commits e evidências quando o ambiente permitir.

## 1. Estado de partida confirmado

- [x] Repositório e branch de desenvolvimento identificados e branch criada.
- [x] Home Builder 5.1.2 localizado; árvore upstream possui 127 arquivos rastreados, incluindo binários, cerca de 11,7 MB. Licença GPL-3.0-or-later; autor Andrew Peel.
- [x] Script de importação preparado: `scripts/import_home_builder.sh`.
- [x] Pontos de extensão preliminares identificados: `operators/doors_windows.py`, `operators/walls.py`, `hb_types.py`, `geometry_nodes/` e UI. Confirmar no código e nos .blend antes de alterar.
- [x] FZM Tile Panels existente em `extensions/fzm_tile_panels/`, com `tile_geometry.py` independente de bpy. FZM Vanity Controls também existe.
- [x] A cópia exata foi importada em clone local. O histórico público requer primeiro a substituição da Calibri nos dois assets identificados na auditoria.
- [x] Identidade FZM, restauração de dependências, ajustes de fonte e smoke headless implementados. Os recursos customizados B–G continuam no backlog.
- [x] Instalação de teste em perfil isolado. Sem publicação do Builder em produção.

## 2. Resultado esperado

Uma única extensão FZM Builder para desenhar paredes, inserir portas/janelas/aberturas, gerar pisos e rodapés por ambiente, pintar paredes e criar shower areas paramétricas. Preservar as ferramentas existentes de paredes, iluminação, plantas de referência, cozinhas, cabinetry, layouts e cortes. O usuário trabalha em pés/polegadas; converter para unidades internas em metros com precisão e manter os campos editáveis. Objetos gerados devem permanecer editáveis e persistir após salvar/reabrir.

**Critérios globais de sucesso**

- [x] Instala e habilita em perfil Linux de teste do Blender 5.1.2 sem traceback.
- [ ] Preserva funções úteis da baseline, inclusive geometria, snapping e edição paramétrica.
- [ ] Portas com design visível nas duas faces e hardware/casings configuráveis.
- [ ] Piso somente em contorno fechado válido; sem vazamento, sem duplicatas e com padrões em escala.
- [ ] Rodapés ligados à área do piso, sem atravessar portas.
- [ ] Pintura global e individual; código Benjamin Moore quando a fonte autorizar, fallback manual.
- [ ] Shower Area inserida e editada como uma unidade; ferramenta Tile existente preservada.
- [ ] Testes automatizados, prova visual interativa, ZIP de pré-release, notas de compatibilidade/rollback.

## 3. Sequência de execução

Estimativas abaixo são esforço de engenharia preliminar por tarefa, não prazos prometidos. Se a tarefa ultrapassar cerca de duas horas, decompor em subtarefas e manter o plano atualizado. Dependências indicadas são gates; não começar refactor destrutivo antes da baseline.

### Fase A — importação e baseline (primeira entrega)

- [x] **A1 — Preparar clone limpo e ferramentas** (30–60 min; sem dependências). Verificar acesso Git de escrita, branch, Blender 5.1.2, ambiente de teste separado; registrar versões e comandos. Não usar tokens em logs.
- [x] **A2 — Importar upstream completo** (30–60 min; A1). Executar comandos abaixo; conferir commit, inventário, binários e licença. Commit de importação separado, sem modificações funcionais.
- [x] **A3 — Auditar empacotamento e licenças** (1–2 h; A2). Verificar Geometry Nodes, assets externos, Git LFS se houver, e wheels Pillow do manifesto para Python 3.13. Resolver dependências com fontes e hashes verificáveis. Verificar licença específica dos assets antes de redistribuir. Não copiar apenas Python nem remover exportação PDF para contornar dependências.
- [x] **A4 — Smoke test da baseline** (1–2 h; A3). Testar habilitação, paredes, portas/janelas/aberturas, comandos de porta, floor/cutter, luzes, planta de referência, cozinha e biblioteca. Registrar resultado e defeitos pré-existentes. Smoke test headless não prova funcionamento da UI.
- [x] **A5 — Identidade da derivação e isolamento** (1–2 h por subetapa; A4). Auditar nomes de operadores, propriedades Scene/Object, handlers, drivers, asset libraries, preferences, IDs e imports; escolher estratégia mínima segura. Nome FZM Builder, ID fzm_builder. Preservar compatibilidade das cenas e referências internas. Não fazer substituição textual global cega. Até provar coexistência, utilizar perfil separado com apenas uma extensão habilitada.
- [x] **A6 — Build de teste** (1–2 h; A5). Gerar ZIP instalável fora do índice de produção, verificar instalação e desinstalação; comparar baseline. Registrar hash do ZIP.

Importação da referência exata (somente em clone local de desenvolvimento):
```bash
git clone https://github.com/felipezabeu/FZM-Blender-Tools.git
cd FZM-Blender-Tools
git switch dev/fzm-builder
git status --short
# Apenas se extensions/fzm_builder ainda não existir:
bash scripts/import_home_builder.sh
git status --short
# Após conferir inventário e licença:
git add extensions/fzm_builder
git commit -m "Import Home Builder 5.1.2 pinned upstream"
```
Se o código já estiver presente, valide o inventário e continue. O commit de referência com a Calibri original fica restrito à baseline local. Consulte o registro de execução para reconstruir o pacote FZM.

### Fase B — Doors (prioridade alta)

- [ ] **B1 — Diagnóstico das duas faces** (1–2 h; A6). Inspecionar node groups e assets, distinguir slab, painéis decorativos, frame, casing e ferragens. Fazer fixture com porta de face única e capturas frente/trás.
- [ ] **B2 — Design bilateral** (1–2 h por perfil; B1). Corrigir geometria/reuso dos detalhes na segunda face, com orientação e normais corretas, mantendo uma folha de espessura correta. Não duplicar a folha inteira, nem espelhar o conjunto de forma que destrua swing ou handing. Testar frente/trás e porta aberta.
- [ ] **B3 — Casings** (1–2 h por subetapa; B1). Criar perfis Flat, Colonial, Step Bevel com largura/espessura configuráveis e encontros corretos; aplicar nos dois lados da abertura, com parâmetros persistentes. Reusar recursos existentes quando disponíveis.
- [ ] **B4 — Hardware** (1–2 h; B1). Escolher Knob ou Lever; ambos os lados, posicionamento correto em portas simples/duplas e mudanças de mão. Acabamentos opcionais: Matte Black, Brushed Nickel, Chrome, Brushed Gold.
- [ ] **B5 — Door Prompts e regressões** (1–2 h por subetapa; B2–B4). Integrar as opções no menu existente. Manter flip swing, flip hand, toggle double, duplicate, delete, abrir/fechar, redimensionar, corte da parede e controles atuais. Testar combinações de perfil/hardware, folha simples/dupla, esquerda/direita, inside/outside, salvar/reabrir, undo. Se o upstream inspecionado diferir da instalação, documentar antes de alterar.

### Fase C — Room Floor (contorno)

- [ ] **C1 — Auditar algoritmo existente** (1–2 h; A6). Revisar find_wall_chains, get_room_boundary_points, is_closed_loop, add_floor em operators/walls.py. Reproduzir quadrado, L, perímetro aberto, paredes invertidas, dois ambientes com parede comum, T-junction e portas.
- [ ] **C2 — Polígonos internos válidos** (1–2 h por subetapa; C1). Extrair/ajustar matemática testável; contorno de faces internas, tolerância explícita, interseções e orientação, sem fechar lacunas artificialmente. Tratar casos ambíguos com mensagem clara. Janelas/portas não rompem o grafo lógico de paredes. Selecionar um ambiente fechado; preferir clique interno se viável.
- [ ] **C3 — Piso por ambiente** (1–2 h; C2). Gerar/atualizar sem duplicar, preservar Floor Cutter. Base upstream de 10 mm pode permanecer para boolean; espessura visual de peças não é exigida. Identificar ambiente, permitir refresh explícito e evitar depender de nomes mutáveis.
- [ ] **C4 — Testes de limites** (1–2 h; C3). Validar área, contorno fechado, concavidade, divisórias, aberturas e níveis. Não preencher áreas externas nem perímetros abertos. Verificar cortes e salvar/reabrir.

### Fase D — Floor Finishes

- [ ] **D1 — Spike comparativo** (1–2 h; C3). Comparar shader procedural, imagem gerada/bake e mesh plana com UVs por peça. Avaliar escala real, repetição visual, editabilidade, export, tempo de geração, VRAM/tamanho e qualidade de render. Escolher solução mais simples que cumpra critérios; documentar decisão e medir numa sala típica e numa sala grande. Não criar objetos sólidos por tábua.
- [ ] **D2 — Random Staggered Planks** (1–2 h; D1). Para vinyl/laminate/hardwood: dimensões reais (largura/comprimento), orientação, deslocamento de juntas e variação de cor/texture com seed determinística. Evitar juntas alinhadas artificialmente.
- [ ] **D3 — Herringbone** (1–2 h; D1). Padrão espinha de peixe real, não chevron, sem sobreposições ou lacunas indevidas; dimensões das peças e orientação parametrizáveis. Validar proporções suportadas e mensagem de erro.
- [ ] **D4 — Tiles** (1–2 h; D1). Dimensões das peças, grout, direção, padrão stack/brick conforme aplicável. Reusar matemática de Tile Panels quando fizer sentido; não impor espessura de tile.
- [ ] **D5 — Painel e texturas** (1–2 h por subetapa; D2–D4). Persistir dimensões, seed, orientação, cor e textura de produto opcional. Alinhar escala UV em metros/polegadas, recortar acabamento ao perímetro côncavo e evitar z-fighting. Fallback sem textura. Testar edição/regeneração e visualização de perto/longe.

### Fase E — Baseboards

- [ ] **E1 — Traçado do rodapé** (1–2 h; C3). Usar mesmo perímetro do piso; excluir intervalos de portas/aberturas e clearance dos casings. Respeitar a regra: sem piso/ambiente válido, sem rodapé automático.
- [ ] **E2 — Perfis e cantos** (1–2 h por subetapa; E1). Flat, Colonial, Step Bevel; altura, espessura, cor/material. Cantos internos/externos mitrados, acabamento nas extremidades; não interferir com abertura.
- [ ] **E3 — Gestão do conjunto** (1–2 h; E2). Um grupo/controle de ambiente, atualização sem duplicação, excluir opcionalmente uma parede/trecho. Validar sala retangular/L, portas simples/duplas, multiple rooms, edição das paredes e persistência.

### Fase F — Wall Paint

- [ ] **F1 — Aplicação de material** (1–2 h; A6). Reutilizar apply_wall_material e entradas Inside/Outside Face etc. Modos All Walls, Selected Walls e reset ao padrão; distinguir aplicação global que substitui overrides de alteração da cor padrão que os preserva. Current Room após C3 se adequado. Testar faces, duplicação, redimensionar, persistência.
- [x] **F2 — Investigação Benjamin Moore** (1–2 h; A6). Verificar fonte oficial/licenciada e condições de uso dos dados de cores; não presumir API pública nem autorização de scraping. Normalizar OC65/OC-65, armazenar código, nome, RGB sRGB e origem quando permitido; conversão correta sRGB para linear Blender. OC-65 é exemplo de lookup, não inventar valor RGB.
- [ ] **F3 — UI, fallback e teste** (1–2 h; F1/F2). Campo de código, cor prévia, manual HEX/RGB e seletor; cache local permitido; erro amigável offline/código desconhecido. Nenhuma requisição obrigatória para usar a ferramenta; preview não é garantia de correspondência física da tinta. Se licença/dados não estiverem disponíveis, entregar modo manual sem inventar catálogo.

### Fase G — FZM Shower Area

- [ ] **G1 — Controller e geometria** (1–2 h por subetapa; A6). Aproveitar fzm_tile_panels/tile_geometry.py; um controlador paramétrico para 2 ou 3 paredes, largura/profundidade/altura, alturas independentes e pony wall opcional com largura/altura/posição. Inserir uma vez e editar conjunto. Manter FZM Tile Panels anterior sem regressões.
- [ ] **G2 — Acabamentos coordenados** (1–2 h; G1). Dimensões das peças, padrão, grout, offsets comuns e alinhamento entre paredes; material padrão e overrides opcionais. Testar cantos/recortes e não sobrepor superfícies.
- [ ] **G3 — UI e persistência** (1–2 h; G2). Recriar somente filhos gerenciados ao alterar parâmetros, sem destruir objetos do usuário. Testar 2/3 paredes, alturas diferentes, meia parede, mover/rotacionar e salvar/reabrir.
- Backlog não obrigatório para primeira versão: niche, bench, curb/curbless, shower floor próprio, vidro, acessórios e quantitativos. Só iniciar após os módulos essenciais.

### Fase H — Validação e entrega

- [ ] **H1 — Regressão automatizada** (1–2 h por suíte; B–G). Python puro para matemática, Blender 5.1.2 headless com fixtures sintéticas, render/capturas quando possível. Medir objetos, vértices, tempo de geração e tamanho. Registrar comando, versões, pass/fail e limitações.
- [ ] **H2 — Teste prático Windows** (depende do proprietário; H1). Roteiro: desenhar banheiro fechado e aberto, inserir e redimensionar porta, trocar perfil/casing/lever, swing/hand, aplicar piso nos três padrões, rodapé, cores e shower area, adicionar iluminação e planta. Salvar/reabrir, undo, conferir Asset Browser. Registrar capturas de antes/depois.
- [ ] **H3 — Pré-release** (1–2 h; H1, H2 se disponível). ZIP isolado com licença, changelog, manual, migração e rollback, checksum. Identificar claramente itens não validados na UI.
- [ ] **H4 — Publicação** (1–2 h; aprovação do proprietário após H2/H3). Revisar PR e diff, somente então integrar a rotina existente de Pages e publicar em https://felipezabeu.github.io/FZM-Blender-Tools/index.json. Não alterar extensões existentes nem deploy automático até aprovação.

## 4. Requisitos de qualidade / riscos

| Risco | Mitigação |
|---|---|
| Upstream binário incompleto ou dependência ausente | Importação Git rastreada, inventário, build real, verificar wheels e assets |
| Conflito com Home Builder | Perfil isolado, auditar registro e migração, não habilitar ambos até teste |
| Door swing e booleans quebrados | Fixtures e testes de todas as combinações, preservar node groups/drivers |
| Piso vazando ou duplicado | Validar topologia e área, tolerância explícita, identidade de ambiente e teste concavidade |
| Geometria pesada | Uma superfície/material por piso, sem milhares de objetos; medir antes de escolher |
| Cor de tinta não autorizada ou inexata | Fonte autorizada, fallback manual, não copiar catálogo, preview aproximado |
| Perda de projetos/bibliotecas | Testar em cópias sintéticas, não tocar arquivos reais; ZIP e rollback |
| Escopo infinito | Gates por módulo, preservar funcionalidades existentes, features extras no backlog |

## 5. Handoff / modo de trabalho

Ao iniciar, leia este plano, o README do repositório e o script de importação. Inspecione branch e arquivos reais; atualize status com evidências. Execute A1–A6 antes de modificar portas. Faça commits separados e pequenos; ao concluir cada fase, registrar no próprio documento commit(s), testes executados, resultados, bloqueios e próxima tarefa. Se for necessário interromper a sessão, outro executor deve conseguir continuar a partir desse estado.

Contexto oficial de governança: [Segundo Cérebro (Drive)](https://drive.google.com/drive/folders/1SEYk2yRI0nsW66grDCGv8iaS-qLIjesC), MAPA.md, skills/MAPA.md e 20_Sistemas_e_Infra/Stack_de_Agentes_e_Ferramentas.md. O GitHub antigo Segundo_Cerebro é legado; este repositório FZM-Blender-Tools é código ativo e local correto para o plano técnico versionado.

## 6. Registro de execução

| Data | Etapa | Evidência / status |
|---|---|---|
| 2026-11-24 | Preparação | Branch criada; script de importação preparado; importação não executada; especificação atualizada. |
| 2026-11-24 | Fase A | Importação local exata, auditoria e suíte A/B no Blender 5.1.2 Linux. Consulte as evidências e decisões abaixo. |
| — | Próxima ação | B1, confirmar de onde vem a folha de uma face vista pelo proprietário e preparar fixture comparativa frente/trás. |


### 6.1 Revisão técnica da baseline

| Frente | Constatação na tag v5.1.2 | Decisão de arquitetura e critério para avançar |
|---|---|---|
| **Fronteira do fork** | O código já concentra snapping e colocação em `hb_snap.py` e `hb_placement.py`. `GeoNodeObject` carrega e reaproveita grupos por nome, e cenas salvas dependem de propriedades `home_builder`, chaves `IS_*_BP`, operadores, menus, sockets e drivers. | Manter a base vendorizada com commit upstream fixo, alterações pequenas por módulo e fixtures para cada atualização. Usar o ID `fzm_builder`, preferências da extensão e prefixos de Asset Library próprios. Preservar identificadores internos que os arquivos existentes usam. Não prometer coexistência com Home Builder 5. O guard cobre a ordem Home Builder habilitado antes do FZM Builder. |
| **Portas e janelas** | `_PlaceWallObjectBase.create_placed_object` cria o cage paramétrico, a legenda e, para portas aplicáveis, `GeoNodeDoorSwing` marcado `IS_2D_ANNOTATION`. Os comandos de mão, sentido e folha dupla mudam sockets da anotação. `GeoNode5PieceDoor` é usado por cabinetry. A tag examinada não fornece folha arquitetônica, batente, casing ou ferragem no fluxo nativo de entrada. | Primeiro identificar como a instalação do proprietário produz a folha de uma face. Para a tag, planejar a geometria visível como filhos gerenciados do cage, com pivô por folha e ferragens filhas. Conservar o cage como cutter e a anotação como representação de planta. Medir se o grupo 5-piece aceita escala, espessura e perfil de porta de entrada antes de reutilizá-lo. Abertura sem folha continua sem swing; batente/casing podem ser independentes. |
| **Piso e ambientes** | `find_wall_chains` liga fim → início em XY com 10 mm, com escolha do primeiro sucessor e um conjunto global de paredes usadas. Paredes invertidas, divisórias compartilhadas, T-junctions e níveis não têm garantia. `is_closed_loop` compara só pontos extremos. `add_floor` produz bounding box se não achar loops; ceiling e lights também usam a infraestrutura de cadeias. | Introduzir um comando FZM de piso estrito inicialmente. Reutilizar triangulação, UV métrico, slab de 10 mm e Floor Cutter. A detecção FZM fica isolada para manter luzes e tetos. Extrair segmentos em coordenadas de mundo a partir dos controles e transformações da parede e classificar suas faces por direção e espessura. Separar níveis, dividir interseções T, caminhar faces delimitadas do grafo e rejeitar contornos ambíguos, inválidos ou externos. O clique seleciona uma face interna; persistir referências dos limites e atualizar o mesmo objeto/mesh em refresh explícito para manter booleans e materiais. |
| **Acabamentos de piso** | O piso já projeta UV planar em metros. Tile Panels trabalha com uma malha por retângulo, mas gera laterais e recorta em retângulo. Sua saída completa não resolve um piso côncavo. | Comparar shader métrico no próprio slab com uma única malha 2D recortada. Shader na superfície do slab segue o recorte do cutter sem segundo sólido. Caso a mídia por peça ou o export exijam malha, medir custo e garantir recorte em contorno e nas áreas removidas pelo cutter. Aproveitar convenções de tamanho, grout, fases e UV de Tile Panels. |
| **Rodapés e casings** | O cutter de portas está ligado ao objeto da abertura e seu tamanho é paramétrico. O upstream também tem assets de crown/cabinetry, com origem e orientação próprias. | Compartilhar somente a seção transversal dos três perfis quando reutilizável. Fazer caminhos separados para rodapé e casing, com intervalos de exclusão projetados das portas/aberturas no limite interno. Deduzir folgas do perfil de casing real. Preservar os vínculos do ambiente para regenerar só filhos gerenciados. |
| **Pintura** | `apply_wall_material` escreve seis sockets das paredes. `GeoNodeWall.assign_materials` contém nomes antigos para quatro sockets, enquanto o asset efetivamente expõe Inside Face, Outside Face, Left Edge e Right Edge, além de Top/Bottom Surface. | Centralizar a lista de sockets a partir do contrato verificado e reutilizar a atribuição nos modos FZM. Manter material padrão, parede override e ação de substituir todos como estados distintos. Começar por HEX/RGB manual com conversão sRGB → linear; Benjamin Moore somente com fonte autorizada. |
| **Shower Area** | `tile_geometry.generate_panel` já fornece paginação, clipping retangular, UV por peça e limites de quantidade. Recebe polegadas e devolve metros. Os offsets são locais a cada painel. | Reusar o módulo MIT com aviso de licença, dentro do pacote Builder quando começar G1. O ZIP deve funcionar sozinho. Até haver motivo para um build compartilhado entre extensões, manter a implementação existente e checar paridade entre as duas cópias. Compor 2–3 painéis sob um controlador e converter unidades em um ponto. Calcular a fase de junta por percurso contínuo ao redor dos cantos e definir a propriedade das bordas conforme espessura e orientação dos painéis. |
| **Persistência e regressão** | `operators/rooms.py` trabalha com cenas de projeto. Um cômodo delimitado para piso é uma entidade dentro de uma dessas cenas. As dimensões já usam metros e os operadores de colocação têm entrada imperial. | Manter a cena de projeto e o ambiente do piso como entidades distintas. Usar propriedades Blender de comprimento e conversões upstream para entrada. Fazer testes A/B com a mesma geometria, salvar/reabrir e testar a UI no Windows para snapping modal, digitação imperial, undo, edição, export e Asset Browser. |

### 6.2 Evidências da primeira entrega

- **Origem e inventário.** A importação local `cf62489` reproduziu a árvore upstream `0395fa0305dabfe5e288713ba61aa4a39a085efa` byte a byte. São 127 arquivos, 27 `.blend`, 35 `.png` e 11.701.920 bytes. Sem Git LFS ou submódulos no material importado. O Git HTTPS deste executor leu os dois repositórios, mas o envio direto não tinha credenciais. O commit `256c048` gravou a revisão e os scripts. O commit de importação desta revisão acrescenta `extensions/fzm_builder` à mesma branch.
- **Licença e ativos.** A licença GPL-3.0-or-later e a atribuição de Andrew Peel acompanham a base. Blender 5.1.2 abriu os 27 `.blend`; a inspeção de IDs não encontrou bibliotecas `.blend` vinculadas nem imagens externas. `assets/` traz o catálogo e os exemplos estão em `product_libraries/`. A versão instalada pelo proprietário e bibliotecas externas continuam pendentes. O arquivo de dimensão traz Calibri embutida e o de retângulo referencia uma cópia do Windows. A importação na branch parte dos mesmos 127 arquivos, com esses dois assets tratados e a identidade FZM aplicada. A árvore final da extensão, validada no clone de desenvolvimento, é `b168fcd93091d52c35edfcf0e351c06545e9b6ee`. O script substitui a fonte por Bfont do Blender e valida ambos reabrindo os arquivos. A troca altera a métrica tipográfica dos textos novos e deve ser inspecionada no Windows. [Versões e licença do Home Builder](https://extensions.blender.org/add-ons/home-builder-5/versions/) · [Licenciamento da Calibri](https://learn.microsoft.com/en-us/typography/font-list/calibri) · [FAQ de redistribuição da Microsoft](https://learn.microsoft.com/en-us/typography/fonts/font-faq)
- **Wheels e builds.** A build original falhou ao tentar incluir o primeiro wheel inexistente. `scripts/prepare_builder_wheels.py` baixou e verificou SHA-256 dos 12 wheels Pillow 12.1.1 do manifesto, para CPython 3.11 e 3.13. A árvore de código continua sem wheels rastreados. O Blender CLI construiu os cinco ZIPs declarados. A execução alvo foi no Blender Linux x64 5.1.2 (`ec6e62d40fa9`, Python 3.13.9), com o SHA-256 oficial do tarball. [Pillow no PyPI](https://pypi.org/project/pillow/12.1.1/) · [Blender 5.1](https://download.blender.org/release/Blender5.1/)
- **Baseline e FZM.** A mesma suíte em perfis isolados passou para ambos. Criação de geometria de parede, porta simples, abertura e janela; boolean na parede; flip de mão e swing; toggle dupla; resize com driver da anotação; delete de janela; piso de 20 m² e slab de 0,20 m³, cortado para 0,19 m³; luzes; imagem de referência empacotada; gabinete base; criação de layout de planta e exportação real de PDF; save/reopen e persistência de dimensões e booleans. O teste de abertura de fixture do Home Builder no FZM passou. O piso legado em perímetro aberto foi reproduzido nas duas versões. Blender registrou avisos de relação VFont e mensagens de render Freestyle/EGL em ambos; o FZM deixou de emitir o erro de arquivo Calibri ausente nas cenas novas.
- **Limitações do smoke.** A colocação usou os métodos de criação/corte da produção por chamadas headless. Snapping modal, controles de viewport, escala interativa da planta, duplicação e undo precisam de teste manual. O teste de layout verificou o PDF produzido e seu formato. A comparação visual da tipografia, da espessura dos traços e dos layouts ficou pendente. Projetos existentes podem manter a fonte original gravada na própria cena.
- **Instalação e desinstalação Linux.** Num perfil separado com FZM Tile Panels 1.0.0 e FZM Vanity Controls 1.2.1, instalei e removi o FZM Builder. Tile Panels gerou 24 peças antes e depois. Vanity Controls permaneceu registrado nas duas verificações. O Asset Library FZM Builder foi removido do perfil.
- **ZIPs de teste validados pelo CLI.** Linux x64 `b5d1c3f77d0e11ce827f78b834571a4c3df13173dfbc9bf2a7d26975fe627164`; Windows x64 `3dac9f380bdd983031b36ab8008f10047f9b4c64e0eb4388e157a01eb99bb9dc`. São hashes desta execução. A build Windows foi validada como arquivo no Linux. Ainda falta instalação, teste e validação visual no Windows.

Reprodução headless a partir da árvore FZM da branch:

```bash
# Defina B como o caminho absoluto do Blender 5.1.2.
python3 scripts/prepare_builder_wheels.py
build_dir="$(mktemp -d)"
export BLENDER_USER_RESOURCES="$(mktemp -d)"
"$B" --command extension build --source-dir extensions/fzm_builder --output-dir "$build_dir" --split-platforms
zip="$build_dir/fzm_builder-5.1.2-linux_x64.zip"
"$B" --command extension validate "$zip"
sha256sum "$zip"
"$B" --command extension install-file -r user_default -e "$zip"
"$B" --background --disable-autoexec --python-exit-code 1 --python scripts/smoke_builder.py -- bl_ext.user_default.fzm_builder --export-pdf
"$B" --command extension remove user_default.fzm_builder
```

Para reproduzir a referência exata de upstream, importe a tag em checkout local isolado, instale o ZIP baseline com ID `home_builder_5` em outro perfil Blender e rode o mesmo script com módulo `bl_ext.user_default.home_builder_5`. O teste de leitura entre versões usa `--save-fixture CAMINHO` na baseline e `--load-fixture CAMINHO` no FZM. Use apenas cenas sintéticas.

---

### 6.3 Build de teste 5.1.3 — paletas locais no Wall Paint

- A build recupera Wall Paint, casings e rodapés do ZIP de acabamentos e acrescenta a leitura de paletas Adobe Swatch Exchange com amostras RGB. O modo **Palette** busca por código ou nome. Equivalências como `OC65` e `OC-65` chegam à mesma entrada. Quando duas coleções fornecem valores diferentes para uma busca, use o campo **Palette File** para selecionar a origem. O material guarda código, nome, arquivo de origem e sRGB.
- Para sincronizar, configure a raiz local da biblioteca FZM em **Preferences → Add-ons → FZM Builder → Asset Libraries**. Coloque os arquivos em `Paletas/Benjamin Moore/` abaixo dessa raiz. **Wall Paint** indexa os arquivos ao abrir e ao aplicar. Para trabalhar offline, mantenha a pasta disponível offline no Drive para desktop. O ícone de pasta ao lado de **Wall Paint** importa um `.ase` no perfil local.
- Para pintar por ambiente, selecione um só piso e abra **Floor & Ceiling → Paint Room Walls**, ou **Wall Paint → Selected Room Floor**. O mesmo menu aceita HEX, RGB e paleta. Só as faces e trechos físicos de parede voltados ao perímetro desse piso recebem tinta. Dois pisos lado a lado podem ter cores diferentes na mesma parede longa; o outro lado de uma divisória física também pode ter outra cor. Vãos de portas e janelas não mudam. Use **Material Preview** ou **Rendered**.
- **Reset Room Paint** remove só os acabamentos daquele piso e volta ao material-base da parede ou ao acabamento de outro piso sobreposto. **Project Default** atualiza a cor-base sem apagar as cores por piso. **All Walls**, **Selected Walls** e **Reset Selected** substituem a pintura inteira das paredes incluídas, inclusive a pintura por piso nelas. Depois de alterar o contorno do piso ou comprimento/traçado da parede, reaplique **Paint Room Walls** para recalcular os trechos.
- O uso de HEX e RGB manual permanece disponível. As paletas originais são fornecidas pelo usuário de acordo com os termos aplicáveis e ficam fora do repositório e do ZIP. [Download oficial das paletas canadenses](https://www.benjaminmoore.com/en-ca/architects-designers/download-benjamin-moore-colour-palettes)
- No Blender 5.1.2 Linux, a suíte `scripts/smoke_paint_palettes.py` exercita criação de material, seleção de origem, pasta compartilhada, importação, persistência e HEX/RGB. Foram verificados os 11 arquivos ASE canadenses distintos disponíveis na página durante o teste, com 3.938 códigos únicos e busca específica por coleção. A Off White oficial foi importada e aplicada no Blender como `OC65` e `OC-65`. Ainda falta validar o diálogo e o Drive sincronizado no Windows.
- Build de desenvolvimento para teste. O workflow de publicação segue no estado anterior. Casings e rodapés dessa build também seguem sujeitos à validação interativa.

### 6.5 Divisor e acabamento do piso

- **Divide Floor** em **Floor & Ceiling**: com o piso ativo, desenhe um segmento de uma borda até a outra. Cada lado vira um piso editável separado, sem uma parede ou outro objeto adicional. Encaixe nas bordas, checagem de contorno, suporte a contornos côncavos quando o segmento permanece dentro do piso e divisões sucessivas. Segmentos incompletos, externos ou sobre uma borda são rejeitados sem alterar o piso. A ferramenta atua sobre a laje existente; não reconstrói automaticamente o contorno se as paredes mudarem. **Add Floor**, teto e luzes mantêm os caminhos anteriores.
- A laje mantém espessura, UV métrico, seleção separada, material inicial e referências a **Floor Cutter**. Aplicar um novo acabamento substitui apenas o material do piso ativo. Um mesmo cutter que atravessa a divisão continua operando nos dois pisos. Os rodapés existentes não são regenerados.
- **Floor Finish**: catálogo local ampliável (Maple, Hickory e Grey Wood genéricos, além de opções neutras), cor sólida e imagem avulsa. Nos acabamentos de madeira, **Board Width** e **Board Length** ajustam as tábuas com juntas desencontradas. Veja em **Material Preview** ou **Rendered**. São detalhes do material, não peças individuais. Se a região tiver **Floor Tile Layout**, o rejunte de tile tem precedência; escolha **No Tile Layout** para voltar às juntas de madeira. Pisos já salvos com o material de madeira antigo não mudam até reaplicar o acabamento. Em uma imagem, indique a largura/altura que a imagem inteira representa. O Blender embute a imagem no arquivo do projeto. Se marcar **Also Save to Local Catalog**, uma cópia da imagem fica no perfil do Blender para outros projetos nesse computador. Não precisa cadastrar uma imagem para usá-la no piso.
- **Paginação**: a branch base não tinha tábuas, tile stack/brick nem herringbone dentro de **Floor & Ceiling**. O novo acabamento não cria nem altera juntas ou paginação. A futura paginação pode reutilizar a escala física, mas fica separada do material. Nenhuma imagem de fornecedor ou referência de produto foi embutida.
- Validação: `scripts/smoke_floor_divider.py` no Blender 5.1.2 Linux headless, cobrindo piso antigo reaberto, dois materiais, textura local e catálogo reutilizável, divisor incompleto/côncavo/sucessivo, cutter atravessando o corte, volumes, UV métrico e reabertura. A execução interativa pelo clique e o teste de instalação no Windows ainda são necessários. Sem publicação em produção.

### 6.6 Portas nativas: closet bypass, bifold e pocket

- Em **Doors & Windows**, **Sliding, Bifold or Pocket Door** escolhe tipo, estilo, tamanho nominal ou medida personalizada. A colocação corta um único vão na parede com o mesmo mecanismo das portas originais. O modelo visível é filho desse vão e largura, altura e espessura acompanham o cage. **Native Door Settings** funciona com a peça visível ou o cage selecionado.
- Estilos: **Flat White**, **White Shaker** e **White Six Panel** para os três tipos, mais **Mirrored** no bypass. As escolhas não modificam outras instâncias. O controle **Open Amount** mostra as posições de projeto. Bifold tem folha dobrada de duas partes; bypass tem duas folhas em trilhos paralelos; pocket reserva lateralmente o equivalente a uma folha ao inserir ou editar.
- A reserva do pocket é uma regra de encaixe do modelo, não uma cavidade usinada nem especificação de obra. O trilho interno é representado e a porta aberta fica atrás do plano da parede. Confirme na obra dimensões, fabricante, cavidade, vão livre e ferragens. Padrões são tamanhos nominais de projeto; não garantem compatibilidade com produtos de catálogo.
- Single Door, Double Door e Open foram preservadas. O novo seletor não transforma portas antigas e não altera a geometria/folha de portas de giro existentes. Knob/lever continuam pendentes de uma folha de giro 3D opt-in: o fluxo anterior tem apenas abertura e anotação de giro.
- `scripts/smoke_native_doors.py` testa implementação, edição, booleana, dimensões, materiais, abertura, restrições, salvamento/reabertura e regressão das portas anteriores no Blender 5.1.2 Linux. O fluxo modal de posicionamento com clique e a interface do Windows ainda precisam de teste interativo. Build local com a versão de Floor 5.1.4 incluída, sem publicação.

### 6.7 Variações Shaker de 1, 2 e 5 painéis

- Em **Doors & Windows → Sliding, Bifold or Pocket Door** ou **Native Door Settings**, escolha **Shaker 1 Panel**, **Shaker 2 Panel** ou **Shaker 5 Panel**. O número é por folha. Flat White, White Six Panel e Mirrored (só bypass) continuam disponíveis. As novas folhas têm painéis rebaixados em uma coluna com travessas horizontais; as travessas se ajustam a folhas bifold estreitas.
- **White Shaker** da 5.1.5 é o mesmo desenho e a mesma opção interna, agora rotulada **Shaker 1 Panel**. Os demais identificadores antigos não mudaram. Um objeto existente mantém seu grupo original, exceto se for editado para usar um dos dois estilos novos; apenas esse objeto passa ao novo grupo e preserva os vínculos de tamanho com o vão.
- Referências de linguagem visual: [Shaker 1](https://www.cosmaroma.com/en/product/1-panel-shaker-interior-door-solid-core/), [Shaker 2](https://www.cosmaroma.com/en/product/2-panel-shaker-solid-core-door-kingstoncosmaroma/), [Shaker 5](https://www.cosmaroma.com/en/product/5-panel-shaker-door-solid-core/) e [Six Panel](https://www.cosmaroma.com/en/product/6-panel-interior-door-wood-grain-hollow-core/), no catálogo Cosmaroma. As geometrias são genéricas, sem cotas nem SKUs do fornecedor. As páginas e referências das imagens foram localizadas; as imagens não estavam disponíveis para conferência visual neste ambiente.
- Testes em Blender 5.1.2: contagem geométrica de painéis em todas as combinações pedidas, janela/corte e movimento visual do pocket sem cavidade construtiva, reabertura, atualização isolada de uma porta de arquivo real da versão 5.1.5 e regressão de Floor. O teste de UI no Windows permanece pendente. Sem mudanças a ferragens de giro nem publicação.

### 6.8 Tile por região e Shower Area (FZM Builder 5.1.7)

- **Floor & Ceiling → Floor Tile Layout** aplica um material de rejunte a um piso ativo, sobre o **Floor Finish** existente. Stack, Brick 50% e Brick 33%, largura/comprimento da peça, rejunte, rotação, cor e deslocamento em unidades do projeto. A malha não muda; o recorte côncavo e buracos de Floor Cutter permanecem. O shader usa o UV de piso em metros, mantém o mapeamento da imagem de fornecedor e não cria peças individuais. Trocar acabamento mantém a paginação; **No Tile Layout** volta ao material-base. Use **Material Preview** ou **Rendered**.
- **Floor & Ceiling → Shower Area** reveste duas ou três paredes paramétricas existentes, contíguas e no mesmo nível, formando um L/U. Cada parede tem limite de altura independente (inclui uma meia parede existente) e corte inicial acima da base. O controlador mantém largura/comprimento dos tiles e fase contínua de rejunte nas quinas. As aberturas da malha de parede avaliada são mantidas, inclusive recortes irregulares, sem modificar paredes/aberturas. Escolha cor ou uma imagem de uma peça, embutida no arquivo. Não seleciona o chão, não cria base, e não modela ladrilhos sólidos, nichos nem impermeabilização. Após mover ou editar paredes, selecione o controlador ou um revestimento e confirme o diálogo novamente para atualizar.
- O módulo canônico **extensions/fzm_tile_panels/tile_geometry.py** fornece dimensões/ciclos de paginação. O ZIP independente do Builder usa uma cópia verificada byte a byte, incluindo licença MIT; **scripts/sync_tile_core.py --check** detecta divergência. **scripts/test_tile_core_parity.py** compara malha e referência analítica, e **scripts/smoke_floor_tiles.py** verifica máscara renderizada pelo Blender. A extensão stand-alone preserva seus operadores e geometria.
- Validação Blender 5.1.2 Linux headless: posições e fases, corte côncavo/Floor Cutter, textura preservada por região, salvar/reabrir, L/U, continuidade nas quinas, corte real de janela e triangular, edição e remoção de revestimento sem tocar no host, portas e Floor anteriores. Esta build de teste não foi publicada. Teste interativo Windows, paginação de madeira/herringbone e novos detalhes construtivos não incluídos.

### 6.9 Nicho e banco em Shower Area (FZM Builder 5.1.8)

- Em **Floor & Ceiling**, selecione o revestimento interno de uma parede com **Shower Area** e use **Add Niche** ou **Add Bench**. Após inserir, selecione a superfície gerada para **Edit Niche/Bench**. O mesmo diálogo ajusta medidas/posição ou remove a peça. Não mova as malhas com G/S: use as medidas do controle. As peças são nativas ao Builder, não arquivos de biblioteca.
- **Custom Tile** é um nicho retangular livre, vertical ou horizontal conforme largura/altura, com ajuste de profundidade, altura a partir da base e distância a partir do início da face indicado pelo caminho do Shower Area. O corte Boolean Exact é não destrutivo, não atravessa a parede em um host suportado, preserva pelo menos 15 mm de parede ao fundo e recorta a malha atual do revestimento. A edição move abertura e acabamentos juntos. A remoção fecha o recorte e mantém as outras aberturas.
- **Marble Prefab | Mayroom K** representa visualmente o [Besso SKU 10230](https://bessofloor.com/products/marble-shower-niche-k), com contorno nominal publicado 13⅞″ × 21⅞″. Marmoreado procedural aproximado. O contorno pode ser exibido alto ou largo; isso não afirma que o produto real possa ser instalado girado. As dimensões de recorte e a profundidade são estimativas editáveis, não valores informados pelo fabricante.
- **Bench** é um corpo retangular apoiado no piso por padrão, 18″ (457,2 mm) de altura inicial, com altura, profundidade e largura parciais ajustáveis, largura inteira da face ou ancoragem em quina a 90°. O banco não altera a parede. Nicho de tile e corpo do banco herdam o material/shader real do revestimento, inclusive a imagem embutida e a fase de juntas. É possível substituir apenas o fundo/assento por cor ou imagem embutida, mantendo a paginação do Shower Area.
- Suporta paredes paramétricas locais em pé, sem escala ou inclinação, com Shower Area previamente criado. Se editar paredes hospedeiras, atualize o **Shower Area** e confira/edite os acessórios; não aplique escala direta, não use um corte manual que se sobreponha à peça e remova/recrie o nicho antes de mudanças grandes de espessura. A verificação é geométrica no Blender, não valida alvenaria, estrutura, impermeabilização ou dimensões de instalação. Hex/Penny ficam pendentes.
- **scripts/smoke_shower_fixtures.py** valida a inclusão via operador, a pele traseira e a profundidade real do nicho, cortes existentes e casos inválidos, movimento, troca de dimensões, banco parcial/de quina e de parede inteira, imagem embutida e material alterado pelo host, as duas orientações do pré-moldado, salvar/reabrir e remoção no Blender 5.1.2 Linux. A build Windows x64 é para teste interativo, sem publicação.

## Anexo: especificação inicial (referência técnica preservada)

# FZM Builder — development plan

Status at drafting. See the execution log above for current status.

## Baseline and distribution
- Upstream: https://github.com/CreativeDesigner3D/home_builder_5
- Tag v5.1.2, commit f345c1710161a4d09149d8ec7b610d0c6f2a9d5e (GPL-3.0-or-later, Andrew Peel). Keep original license, attribution and notices, including asset-specific license checks.
- Import the complete tracked tree using scripts/import_home_builder.sh; do not copy only Python files. The upstream tree includes binary Blender node/asset files. Check the manifest's missing Pillow wheels and upstream build procedure before packaging; do not silently drop PDF export support.
- Target extensions/fzm_builder; make a distinct extension ID, display name, settings/data paths, and operator/property/handler namespaces only after auditing dependencies and migration behavior. Preserve upstream functionality and existing scenes. Until namespace isolation is tested, never enable both extensions in the same Blender profile.
- Keep main and current Pages deployment untouched. Existing FZM Vanity Controls and Tile Panels remain functional. Add Builder packaging to a test release only after verification.

## Work packages and acceptance
1. Import unchanged pinned baseline. Commit import separately; smoke-test Blender 5.1.2 wall drawing, window/opening/door insertion, dimension editing, swing, hand, double, duplicate/delete, lights, imported plan images, layouts, floor cutter, asset libraries and kitchen tools. Record baseline bugs before modifications.
2. Doors: investigate Geometry Nodes and door asset/profile creation plus operators/doors_windows.py. Symmetric front/back leaf design with correctly mirrored details and no duplicated slabs, casing or handles. Provide casing Flat / Colonial / Step Bevel (profile widths editable) and hardware Knob / Lever; both faces, handedness and double leaves. Preserve resize, swing/hand toggles, duplication/deletion and wall cut behavior. Verify one and two leaves, left/right, in/out, dimensions, saved/reopened scenes, all casing/hardware combinations.
3. Room floors: extend operators/walls.py existing find_wall_chains, get_room_boundary_points, is_closed_loop and add_floor. Validate interior finished boundary before creating; do not silently bridge gaps. Support reversed wall directions, concave L rooms, shared walls and T-junctions; click inside selected room; doors/openings do not break the logical wall graph. Explicit room separation at open passages; avoid floor duplicates. Reuse base slab (upstream uses 10 mm for Boolean cutters); visual finish has no required physical thickness. Keep floor cutters and saved parameters. Update from room walls on explicit refresh initially.
4. Floor finishes: one floor finish material/object per room, not one solid per board. Prototype deterministic 2D procedural/polygon pattern or baked reusable texture on planar metric UVs: Random Staggered Planks (vinyl/laminate/hardwood), Herringbone, Tiles. Real-size board width/length, orientation, offsets/seed, variation, seams/grout and tile patterns. Clip to concave room perimeter. Render correct seam scale, avoid visible tiling repetition/moire, bound texture resolution/geometry cost; compare procedural shader vs flat mesh with per-piece UVs. Texture-based variation is acceptable; no mandatory volumetric board mesh. Retain base slab for cutter compatibility; avoid z-fighting. Do not generate per-piece solids by default.
5. Baseboards: generate from the same validated interior floor boundary; exclude door/opening clear widths (and casing clearance), not windows. Flat / Colonial / Step Bevel profiles, adjustable height/thickness/color. Proper inside/outside miter corners; one managed group per room, regenerate without duplicates, no walls altered. Test concave corners, door gaps, shared walls, multiple rooms and height changes.
6. Wall paint: extend existing material application to all walls, selected walls, per-wall override and reset to default; material assignment must survive edits and save/reopen. Optional interior/exterior face choice. Benjamin Moore code lookup normalize OC65 / OC-65 and store name/code/source plus display sRGB; convert to scene-linear correctly. Investigate official digital swatch or appropriately licensed dataset, cache only allowed data. No scraping/bundling entire proprietary catalog without permission; manual HEX/RGB fallback for unknown codes/offline; preview is approximate, not physical paint match.
7. Shower Area: retain existing fzm_tile_panels as standalone until validated; use tile_geometry.generate_panel as shared visual generator, not duplicate the algorithm. One controller for 2/3 walls, optional pony wall, adjustable independent heights and common grout alignment. Separate shower floor/material overrides later. Preserve existing tile panels and project compatibility. 

## Testing / delivery
- Unit-test pure room/pattern math (rectangles, L rooms, reversed walls, open perimeter, multiple rooms, exact sizing, deterministic seed, no overlaps/gaps outside intentional joints).
- Blender 5.1.2 headless integration: create scene, inspect geometry, transforms/materials/node inputs, boolean openings, save/reopen and regenerate; measure object count and update time.
- Interactive Windows smoke tests for modal placement, menus, undo, resizing, floor and profile options. Headless tests cannot substitute for UI tests.
- Separate commits per work package, review regressions; never deploy partial extension to production Pages index. Prefer an installable prerelease ZIP and test profile, then release with changelog and migration notes.

