# Janela 3D opcional

Na barra **N → Home Builder → Room Layout → Doors & Windows**, use **3D Window**
para colocar uma janela ilustrativa com caixilho branco e vidro, ou **Window Opening**
para manter apenas o vão. As duas ferramentas conservam as medidas e os atalhos de
posicionamento existentes.

Selecione o caixilho ou o vão e abra **Window Prompts**. A caixa **Show 3D Window**
liga ou desliga o caixilho e o vidro sem alterar o recorte na parede. Largura,
altura e posição são editadas no mesmo diálogo; confirme em **OK**. As janelas
de arquivos existentes não recebem caixilho automaticamente.

O vidro é translúcido em **Material Preview** ou **Rendered**. Em **Solid**,
ele é mostrado como geometria de prévia, sem simulação de vidro. A janela é
genérica e não representa um produto específico ou um detalhe construtivo.

Teste de integração: `scripts/smoke_window_content.py`, Blender 5.1.2 Linux
em segundo plano. Validação manual no Windows não incluída.
