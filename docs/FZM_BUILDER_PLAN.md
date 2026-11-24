# FZM Builder — plano de execução e handoff

> Criado em 2026-11-24. Status: PLANEJADO / NÃO IMPLEMENTADO. Requisitos aprovados pelo proprietário para iniciar desenvolvimento. Atualizar este arquivo conforme a execução; não declarar etapas concluídas sem evidência.

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
- [!] A cópia integral ainda NÃO ocorreu: tentativa de referenciar a árvore Git upstream pelo conector retornou 422. Executar importação com Git em ambiente que consiga transferir binários.
- [ ] Nenhuma alteração funcional de Builder foi implementada ou testada.
- [ ] Nenhuma extensão Builder foi instalada/publicada; main e GitHub Pages de produção permanecem inalterados.

## 2. Resultado esperado

Uma única extensão FZM Builder para desenhar paredes, inserir portas/janelas/aberturas, gerar pisos e rodapés por ambiente, pintar paredes e criar shower areas paramétricas. Preservar as ferramentas existentes de paredes, iluminação, plantas de referência, cozinhas, cabinetry, layouts e cortes. O usuário trabalha em pés/polegadas; converter para unidades internas em metros com precisão e manter os campos editáveis. Objetos gerados devem permanecer editáveis e persistir após salvar/reabrir.

**Critérios globais de sucesso**

- [ ] Instala e habilita em perfil de teste do Blender 5.1.2 sem traceback.
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

- [ ] **A1 — Preparar clone limpo e ferramentas** (30–60 min; sem dependências). Verificar acesso Git de escrita, branch, Blender 5.1.2, ambiente de teste separado; registrar versões e comandos. Não usar tokens em logs.
- [ ] **A2 — Importar upstream completo** (30–60 min; A1). Executar comandos abaixo; conferir commit, inventário, binários e licença. Commit de importação separado, sem modificações funcionais.
- [ ] **A3 — Auditar empacotamento e licenças** (1–2 h; A2). Verificar Geometry Nodes, assets externos, Git LFS se houver, e wheels Pillow do manifesto para Python 3.13. Resolver dependências com fontes e hashes verificáveis. Verificar licença específica dos assets antes de redistribuir. Não copiar apenas Python nem remover exportação PDF para contornar dependências.
- [ ] **A4 — Smoke test da baseline** (1–2 h; A3). Testar habilitação, paredes, portas/janelas/aberturas, comandos de porta, floor/cutter, luzes, planta de referência, cozinha e biblioteca. Registrar resultado e defeitos pré-existentes. Smoke test headless não prova funcionamento da UI.
- [ ] **A5 — Identidade da derivação e isolamento** (1–2 h por subetapa; A4). Auditar nomes de operadores, propriedades Scene/Object, handlers, drivers, asset libraries, preferences, IDs e imports; escolher estratégia mínima segura. Nome FZM Builder, ID fzm_builder. Preservar compatibilidade das cenas e referências internas. Não fazer substituição textual global cega. Até provar coexistência, utilizar perfil separado com apenas uma extensão habilitada.
- [ ] **A6 — Build de teste** (1–2 h; A5). Gerar ZIP instalável fora do índice de produção, verificar instalação e desinstalação; comparar baseline. Registrar hash do ZIP.

Comandos de partida (somente em clone de desenvolvimento):
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
git push origin dev/fzm-builder
```
Se outro executor já importou o código, validar e continuar; não repetir a importação.

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
- [ ] **F2 — Investigação Benjamin Moore** (1–2 h; A6). Verificar fonte oficial/licenciada e condições de uso dos dados de cores; não presumir API pública nem autorização de scraping. Normalizar OC65/OC-65, armazenar código, nome, RGB sRGB e origem quando permitido; conversão correta sRGB para linear Blender. OC-65 é exemplo de lookup, não inventar valor RGB.
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
| — | Próxima ação | A1 → A2 em ambiente com Git completo. |

---

## Anexo: especificação inicial (referência técnica preservada)

# FZM Builder — development plan

Status: development specification only; no fork is installed or published yet.

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

