document.addEventListener('DOMContentLoaded', () => {
  // =============================
  // Funções de dimensões responsivas
  // =============================
  function getResponsiveDimensions() {
    const screenWidth = window.innerWidth;
    if (screenWidth <= 320) return { width: 180, height: 120, scale: 0.6 };
    if (screenWidth <= 480) return { width: 220, height: 140, scale: 0.7 };
    if (screenWidth <= 768) return { width: 280, height: 160, scale: 0.8 };
    if (screenWidth <= 1024) return { width: 320, height: 180, scale: 0.9 };
    return { width: 350, height: 200, scale: 1.0 };
  }

  // =============================
  // SVG do navio
  // =============================
  const navioSvg = (index) => {
    const { width, height, scale } = getResponsiveDimensions();
    return `
      <svg width="${width}" height="${height}" viewBox="0 0 400 250" xmlns="http://www.w3.org/2000/svg" style="max-width:100%; height:auto;">
        <rect x="0" y="180" width="400" height="70" fill="#0077be" />
        <path d="M30,180 Q200,220 370,180 L370,250 Q200,230 30,250 Z" fill="rgba(255,255,255,0.2)" />
        <path d="M50,150 L350,150 L330,180 L70,180 Z" fill="#1a3a7d" />
        <path d="M70,120 L330,120 L350,150 L50,150 Z" fill="#2a4b8d" />
        <rect x="100" y="100" width="200" height="20" fill="#34495e" rx="2" />
        <g id="navioContainers${index}">
          <rect x="110" y="105" width="30" height="15" fill="#e74c3c" />
          <rect x="150" y="105" width="30" height="15" fill="#f39c12" />
          <rect x="190" y="105" width="30" height="15" fill="#2ecc71" />
          <rect x="230" y="105" width="30" height="15" fill="#3498db" />
          <rect x="110" y="85" width="30" height="15" fill="#9b59b6" />
          <rect x="150" y="85" width="30" height="15" fill="#1abc9c" />
          <rect x="190" y="85" width="30" height="15" fill="#d35400" />
          <rect x="230" y="85" width="30" height="15" fill="#7f8c8d" />
        </g>
        <text x="200" y="95" text-anchor="middle" font-size="${Math.max(10,12*scale)}" fill="white" font-weight="bold">NAVIO ${index+1}</text>
      </svg>
    `;
  };

  // =============================
  // Template da grua
  // =============================
  const gruaTemplate = (index) => {
    const { width, height, scale } = getResponsiveDimensions();
    return `
      <div class="grua-container" style="position:relative; margin-bottom: 10px;">
        <svg width="${width}" height="${height}" viewBox="0 0 400 250" xmlns="http://www.w3.org/2000/svg" style="max-width:100%; height:auto;">
          <!-- Estrutura da grua -->
          <rect x="180" y="50" width="40" height="150" fill="#5D8AA8" rx="2" />
          <rect x="170" y="40" width="60" height="10" fill="#4A708B" rx="2" />
          <rect id="braco${index}" x="20" y="40" width="360" height="20" fill="#6E7B8B" rx="2" />
          
          <!-- Carrinho da grua -->
          <g id="carrinho${index}" transform="translate(180,0)">
            <rect x="0" y="35" width="40" height="25" fill="#FFD700" rx="2" />
            <!-- Cabo da grua -->
            <line id="cabo${index}" x1="20" y1="60" x2="20" y2="85" stroke="#555" stroke-width="2" />
            <!-- Gancho da grua -->
            <g id="gancho${index}" transform="translate(20,85)">
              <path d="M-5,0 L5,0 L5,8 L0,13 L-5,8 Z" fill="#333" />
            </g>
          </g>
          
          <!-- Container que será movido -->
          <g id="containerMovel${index}" style="display:none;">
            <rect x="-20" y="13" width="40" height="25" fill="#FFA500" stroke="#333" stroke-width="1" rx="2" />
          </g>

          <!-- Estado OFF -->
          <g id="offState${index}" style="display:none;">
            <rect x="160" y="70" width="80" height="40" fill="rgba(0,0,0,0.7)" rx="4" />
            <text x="200" y="95" text-anchor="middle" font-size="${Math.max(12,16*scale)}" fill="white" font-weight="bold">GRUA OFF</text>
          </g>
        </svg>
      </div>
    `;
  };

  // =============================
  // Função para animar a grua
  // =============================
  // =============================
// Função para animar a grua
// =============================
function criarGrua(index) {
    const isMobile = window.innerWidth <= 768;
    const velocidadeVertical = isMobile ? 0.6 : 0.6;
    const velocidadeHorizontal = isMobile ? 0.6 : 0.6;
    const tempoPausa = isMobile ? 2000 : 2000;
    const tempoPausa_pegando = isMobile ? 50 : 50;

    const navioContainers = document.getElementById(`navioContainers${index}`);
    const containerMovel = document.getElementById(`containerMovel${index}`);
    const braco = document.getElementById(`braco${index}`);
    const carrinho = document.getElementById(`carrinho${index}`);
    const cabo = document.getElementById(`cabo${index}`);
    const gancho = document.getElementById(`gancho${index}`);
    const offState = document.getElementById(`offState${index}`);

    let containerIndex = 0;
    let carrinhoX = 180;
    let comprimentoCabo = 85;
    let state = 'descendo';
    let animationId = null;
    let working = false;
    
    // Controle de tempo para velocidade consistente
    let ultimoTempo = 0;
    const fps = 60; // Frames por segundo
    const intervaloFrame = 1000 / fps;

    function animate(tempoAtual) {
        if (!working) return;

        // Controla a velocidade baseada no tempo
        const deltaTempo = tempoAtual - ultimoTempo;
        if (deltaTempo < intervaloFrame) {
            animationId = requestAnimationFrame(animate);
            return;
        }
        ultimoTempo = tempoAtual;

        switch(state) {
            case 'descendo':
                comprimentoCabo += velocidadeVertical;
                if (comprimentoCabo >= 120) {
                    comprimentoCabo = 120;
                    state = 'pegando';
                    setTimeout(() => {
                        containerMovel.style.display = 'inline';
                        const rectMovel = containerMovel.querySelector('rect');
                        const navioRect = navioContainers.children[containerIndex];
                        
                        if (rectMovel && navioRect) {
                            rectMovel.setAttribute('fill', navioRect.getAttribute('fill'));
                            navioRect.style.opacity = '0.3';
                        }
                        state = 'subindo';
                    }, tempoPausa_pegando);
                }
                break;

            case 'subindo':
                comprimentoCabo -= velocidadeVertical;
                if (comprimentoCabo <= 40) {
                    comprimentoCabo = 40;
                    state = 'movendo';
                }
                break;

            case 'movendo':
                carrinhoX += velocidadeHorizontal;
                if (carrinhoX >= 300) {
                    carrinhoX = 300;
                    state = 'depositando';
                    setTimeout(() => {
                        containerMovel.style.display = 'none';
                        const navioRect = navioContainers.children[containerIndex];
                        if (navioRect) {
                            navioRect.style.display = 'none';
                        }
                        
                        containerIndex++;
                        
                        if (containerIndex >= navioContainers.children.length) {
                            containerIndex = 0;
                            for (let c of navioContainers.children) {
                                c.style.display = 'inline';
                                c.style.opacity = '1';
                            }
                        }
                        
                        carrinhoX = 180;
                        comprimentoCabo = 85; // Corrigido: estava 500
                        state = 'descendo';
                    }, tempoPausa);
                }
                break;
        }

        carrinho.setAttribute('transform', `translate(${carrinhoX},0)`);
        cabo.setAttribute('y2', comprimentoCabo);
        gancho.setAttribute('transform', `translate(20,${comprimentoCabo})`);
        containerMovel.setAttribute('transform', `translate(${carrinhoX + 20},${comprimentoCabo + 13})`);

        animationId = requestAnimationFrame(animate);
    }

    function atualizar(on) {
        working = on;
        if (on) {
            braco.setAttribute("fill", "#6E7B8B");
            offState.style.display = 'none';
            if (state === 'descendo') {
                carrinhoX = 180;
                comprimentoCabo = 85;
                containerMovel.style.display = 'none';
            }
            ultimoTempo = performance.now(); // Reinicia o controle de tempo
            animate(ultimoTempo);
        } else {
            braco.setAttribute("fill", "#9E9E9E");
            containerMovel.style.display = 'none';
            offState.style.display = 'inline';
            if (animationId) {
                cancelAnimationFrame(animationId);
                animationId = null;
            }
        }
    }

    return atualizar;
}
 

  // =============================
  // Inicializar porto
  // =============================
  const porto = document.getElementById("porto");
  if (!porto) {
    console.error('Elemento #porto não encontrado');
    return;
  }

  const screenWidth = window.innerWidth;
  const totalNavios = screenWidth <= 480 ? 1 : screenWidth <= 768 ? 2 : screenWidth <= 1024 ? 3 : 4;

  const gruas = [];

  // Limpa o porto antes de adicionar novos elementos
  porto.innerHTML = '';

  for (let i = 0; i < totalNavios; i++) {
    const div = document.createElement("div");
    div.className = "navio-container";
    div.id = `navioContainer${i}`;
    div.style.position = 'relative';
    div.style.marginBottom = '20px';
    div.innerHTML = gruaTemplate(i) + navioSvg(i);

    // div.innerHTML = `
    <div class="grua-titulo" style="text-align:center; font-weight:bold; margin-bottom:5px;">
      Grua ${i + 1}
    </div>
    ${gruaTemplate(i)}
    ${navioSvg(i)}
`;
    porto.appendChild(div);
    gruas.push(criarGrua(i));
    
    // Inicialmente desliga todas as gruas
    gruas[i](false);
  }

  // =============================
  // Atualizar estado do cais via API
  // =============================
  async function atualizarEstadoCais() {
    try {
      const res = await fetch('/api/v1/estado-cais');
      
      if (!res.ok) {
        throw new Error(`Erro HTTP: ${res.status}`);
      }
      
      const cais = await res.json();
      console.log('Dados recebidos da API:', cais);

      // Ordena os cais por berth_id para garantir a correspondência correta
      const caisOrdenados = cais.sort((a, b) => a.berth_id - b.berth_id);
      
      caisOrdenados.forEach((caisItem, index) => {
        // Verifica se existe uma grua para este índice
        if (index < gruas.length) {
          const containerDiv = document.getElementById(`navioContainer${index}`);
          if (!containerDiv) return;
          
          const ocupado = caisItem.ocupado;
          
          if (ocupado) {
            containerDiv.style.display = 'block';
            containerDiv.classList.remove('oculto');
            gruas[index](true);
            console.log(`Grua ${index} (Berth ${caisItem.berth_id}): LIGADA - Ocupado`);
          } else {
            containerDiv.classList.add('oculto');
            setTimeout(() => {
              containerDiv.style.display = 'none';
            }, 600);
            gruas[index](false);
            console.log(`Grua ${index} (Berth ${caisItem.berth_id}): DESLIGADA - Livre`);
          }
        }
      });

    } catch (error) {
      console.error('Erro ao atualizar estado do cais:', error);
      
      // Em caso de erro, mantém o estado atual sem alterações
      console.log('Mantendo estado atual das gruas devido ao erro na API');
    }
  }

  // =============================
  // Inicialização
  // =============================
  console.log('Inicializando sistema de gruas no frontend...');
  console.log(`Número de gruas criadas: ${gruas.length}`);

  // Atualiza imediatamente e depois a cada 5 segundos
  atualizarEstadoCais();
  const intervalo = setInterval(atualizarEstadoCais, 5000);

  // =============================
  // Gerenciamento de redimensionamento
  // =============================
  let resizeTimeout;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimeout);
    clearInterval(intervalo); // Limpa o intervalo antigo
    resizeTimeout = setTimeout(() => {
      console.log('Redimensionamento detectado, recarregando...');
      window.location.reload();
    }, 500);
  });

  // =============================
  // Limpeza ao sair da página
  // =============================
  window.addEventListener('beforeunload', () => {
    clearInterval(intervalo);
    clearTimeout(resizeTimeout);
    gruas.forEach(grua => grua(false));
  });
});