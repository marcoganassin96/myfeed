<?php
namespace App;

use Symfony\Bundle\FrameworkBundle\Kernel\MicroKernelTrait;
use Symfony\Component\DependencyInjection\Compiler\CompilerPassInterface;
use Symfony\Component\DependencyInjection\Compiler\PassConfig;
use Symfony\Component\DependencyInjection\ContainerBuilder;
use Symfony\Component\HttpKernel\Kernel as BaseKernel;

class Kernel extends BaseKernel
{
    use MicroKernelTrait;

    protected function build(ContainerBuilder $container): void
    {
        // Priority 10 ensures this runs before RegisterControllerArgumentLocatorsPass (priority 0),
        // which builds the allowControllers whitelist from controller.service_arguments tags.
        $container->addCompilerPass(new class implements CompilerPassInterface {
            public function process(ContainerBuilder $container): void
            {
                foreach (['nelmio_api_doc.controller.swagger_ui', 'nelmio_api_doc.controller.swagger_json'] as $id) {
                    if ($container->hasDefinition($id)) {
                        $container->getDefinition($id)->addTag('controller.service_arguments');
                    }
                }
            }
        }, PassConfig::TYPE_BEFORE_OPTIMIZATION, 10);
    }
}
