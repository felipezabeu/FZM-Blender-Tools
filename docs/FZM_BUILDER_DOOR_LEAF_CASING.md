# Folhas de giro e guarnições no FZM Builder

## Folha 3D

- Abra **N → Home Builder → Doors & Windows**. Uma nova **Single Door** ou **Double Door** mostra a folha fechada em 3D, quando o vão tem tamanho compatível. **Open** continua só como vão. Portas antigas não são modificadas automaticamente.
- Selecione a folha ou o vão e abra **Edit Door** na barra lateral ou menu de contexto. **Show 3D Leaf** liga/desliga, **Leaf Style** troca Flat White, Shaker 1/2/5 ou White Six Panel e **Open Amount** gira a folha até 90°. **Swing Direction** e **Door Hand** (Single) também ficam no mesmo diálogo. As escolhas são por porta. Os estilos das portas de correr, bifold e pocket também ficam em **Edit Door**.
- O vão original continua recortando a parede. As dimensões da folha acompanham as do vão, não o contrário. A anotação 2D mantém o comportamento anterior. Desligar a folha mantém dimensões, abertura e preferências de estilo. A folha é de visualização, sem novo batente, dobradiça ou maçaneta e sem garantia de folgas construtivas.

## Door Casing

- Selecione várias portas/folhas com Shift e use **Door Casing → Apply To → Selected Doors**. A mesma configuração é aplicada uma vez a cada vão, mesmo que a folha e o vão estejam ambos selecionados. A guarnição continua acompanhando largura, altura e espessura individuais.
- **All Doors in This Scene** é um escopo explícito para todos os vãos locais da cena aberta, sem incluir outras cenas. Também funciona para **Remove Casing**. Abrir o diálogo não muda nada.
- **Colonial** agora usa um perfil em S suave, com ressalto interno baixo e borda externa arredondada. Guarnições Colonial já salvas continuam iguais até reaplicar o perfil. **Room Baseboards** não muda.

Verificação: Blender 5.1.2 Linux headless, scripts `smoke_hinged_casing.py` e `smoke_native_doors.py`. Asserções de recorte, material/rebaixos, pose de giro, largura, altura, inclusão e retenção de guarnições, escopo, remoção e reabertura. Teste interativo no Windows pendente.
